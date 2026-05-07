# Chat V2 Sandbox — Empirical bwrap Findings

**Date:** 2026-04-27
**Author:** Jack Musick + Claude
**Status:** Reference notes for sub-project (4) Code Execution
**Companion to:** `2026-04-27-chat-v2-program-design.md`

This is a record of what we learned by actually running `bwrap` (bubblewrap), the kernel sandbox primitive that Anthropic's `sandbox-runtime` wraps, in real environments. The point is to prevent a future spec from re-doing this work.

The TL;DR up front: getting bwrap to run inside a normal Docker/K8s container is more involved than the marketing makes it sound. Several layers of host- and container-level security policy each need to permit the kernel features bwrap depends on. Three of those layers are off-by-default on common platforms.

## What `sandbox-runtime` is, mechanically

`sandbox-runtime` is an Apache-2.0 wrapper around bubblewrap (`bwrap`) that produces a sandboxed process — restricted filesystem view, restricted network, namespace isolation. It is a binary you invoke as a subprocess. It is **not** a container runtime, **not** a VM, and does **not** require Docker or K8s.

Under the hood it calls `bwrap`, which calls a bunch of kernel syscalls — primarily `unshare(2)` with various `CLONE_NEW*` flags — to construct nested namespaces (user, mount, pid, network, ipc, uts, cgroup) for the child process. The child runs in those namespaces and sees only what bwrap mounts/binds into them.

bwrap is "unprivileged" in the sense that it does not need the setuid bit, does not need `CAP_SYS_ADMIN` granted to the calling process, and does not need to run as root. But it does need the kernel to **allow** unprivileged user namespaces — which is where the layers of policy come in.

## The four layers that can block bwrap

When you try to run bwrap from inside a container, the call chain has to pass through four security layers, in order:

```
              [bwrap process inside container]
                       │
                       ▼
   ┌─────────────────────────────────────────────┐
   │ 1. Container seccomp profile                │  ← Docker's default blocks unshare(CLONE_NEWUSER) here
   └─────────────────────────────────────────────┘
                       │
                       ▼
   ┌─────────────────────────────────────────────┐
   │ 2. Container AppArmor profile (docker-default) │  ← can deny userns
   └─────────────────────────────────────────────┘
                       │
                       ▼
   ┌─────────────────────────────────────────────┐
   │ 3. Host AppArmor (kernel.apparmor_restrict_unprivileged_userns) │  ← Ubuntu 23.10+ default = restrict
   └─────────────────────────────────────────────┘
                       │
                       ▼
   ┌─────────────────────────────────────────────┐
   │ 4. Host kernel sysctl (user.max_user_namespaces) │  ← Bottlerocket default = 0
   └─────────────────────────────────────────────┘
                       │
                       ▼
                [kernel grants/denies unshare]
```

Each layer is a separate policy decision. Disabling AppArmor doesn't help if seccomp blocks the call. Enabling the host sysctl doesn't help if Docker's seccomp profile blocks it before it reaches the host.

## Empirical test on Ubuntu 24.04 host + python:3.14-slim worker image (2026-04-27)

Tested live on the dev machine. Host: `Ubuntu 24.04.3 LTS`, kernel `6.8.0-110-generic`. Container image: `python:3.14-slim` (Debian 13 / trixie inside).

| Configuration | Result |
|---|---|
| `bwrap` directly on host (host sysctl `apparmor_restrict_unprivileged_userns=1`, the default) | ❌ `Operation not permitted` |
| `bwrap` directly on host (host sysctl flipped to `0`) | ✅ works |
| `docker run python:3.14-slim ... bwrap ...` (default) | ❌ `Operation not permitted` (CLONE_NEWNS path) |
| Same with `--security-opt apparmor=unconfined` | ❌ same |
| Same with `--security-opt seccomp=unconfined` | ❌ same (AppArmor blocks) |
| Same with `apparmor=unconfined` + `seccomp=unconfined` (host sysctl still `1`) | ❌ "kernel does not allow non-privileged user namespaces" |
| Same, host sysctl flipped to `0`, `--unshare-user` flag added | ✅ basic bwrap works |
| Full `--unshare-all --proc /proc` | ❌ `Can't mount proc on /newroot/proc: Operation not permitted` |
| Full sandbox using `--ro-bind /proc /proc` instead of remounting proc | ✅ everything works (Python 3 ran, network namespace isolated, no host network access) |

### Concrete recipe that works on Ubuntu 24.04 host with `python:3.14-slim` container

**Host setup (one-time):**
```bash
sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0
# Persist via /etc/sysctl.d/10-bifrost-sandbox.conf
```

**Container run flags:**
```bash
docker run \
    --security-opt apparmor=unconfined \
    --security-opt seccomp=unconfined \
    python:3.14-slim ...
```

**bwrap invocation that works (note: ro-bind /proc, NOT --proc /proc, to avoid the PID-namespace proc-remount issue):**
```bash
bwrap \
    --unshare-user \
    --unshare-net \
    --unshare-ipc \
    --unshare-uts \
    --unshare-cgroup \
    --bind /tmp/work /work \
    --ro-bind /usr /usr \
    --ro-bind /lib /lib \
    --ro-bind /lib64 /lib64 \
    --ro-bind /etc /etc \
    --ro-bind /bin /bin \
    --ro-bind /proc /proc \
    --dev /dev \
    --die-with-parent \
    python3 /work/main.py
```

This produces a sandboxed child where:
- Filesystem is bind-mounted read-only with a single writable scratch dir at `/work`.
- Network namespace is isolated (no inbound or outbound network).
- IPC, UTS, cgroup namespaces are isolated.
- Parent `simple_worker.py` death kills the child via `--die-with-parent`.
- `/proc` is the host container's proc, ro-bound. We chose this over creating a fresh PID namespace because `--proc /proc` requires `mount(... MS_NOSUID|MS_NODEV ..., proc, ...)` which Docker blocks even with all other knobs off.

### Why we don't get a fresh PID namespace

The classic bwrap recipe also calls `--unshare-pid --proc /proc` so the sandboxed process sees its own PID 1 and a clean process table. We can't do that inside a Docker container without elevated privileges, because remounting proc inside a new PID namespace is itself a privileged mount operation that Docker's default mount restrictions block.

The trade-off: the sandboxed process can `cat /proc/<pid>/cmdline` and see the worker process and other host processes. This is information disclosure, not a privilege grant — they can read but not interact, because the user, network, and IPC namespaces remain isolated and the sandboxed UID has no meaningful privileges in the container's namespaces. Acceptable for v1; revisit if we need stronger PID isolation.

## Per-platform reality (verified 2026-04)

| Platform | Host sysctl | Host AppArmor | Container seccomp | Container AppArmor | Operator action |
|---|---|---|---|---|---|
| **DOKS** (Debian 12) | OK | OK | needs override (default blocks `unshare`) | OK | Pod must set `seccomp=Unconfined` or use a custom profile |
| **GKE** (COS) | OK | OK | needs override | OK | Same |
| **EKS / Amazon Linux 2023** | OK | OK | needs override | OK | Same |
| **EKS / Bottlerocket** | **needs override** (`user.max_user_namespaces`) | OK | needs override | OK | Bottlerocket node user data + pod seccomp |
| **AKS / Azure Linux 3.0** | OK | OK | needs override | OK | Pod seccomp |
| **AKS / Ubuntu 24.04** | OK | **needs override** (`apparmor_restrict_unprivileged_userns`) | needs override | needs override | Host sysctl + pod seccomp + pod AppArmor |
| **Local Docker on Debian 12 / Ubuntu 22.04** | OK | OK | needs override | OK | Compose `security_opt` with `seccomp=unconfined` |
| **Local Docker on Ubuntu 24.04** | OK | **needs override** | needs override | needs override | Sysctl + Compose security_opt for both seccomp and apparmor |

The pattern: **`seccomp=Unconfined` is required everywhere**, because Docker's default seccomp profile (which K8s also uses as RuntimeDefault) blocks `unshare(CLONE_NEWUSER)` for non-`CAP_SYS_ADMIN` callers. This is a hard requirement of the sandbox-as-child-process design.

## Earlier spec claim that was wrong

The committed program-level spec (`2026-04-27-chat-v2-program-design.md`) initially said the worker pod stays "unprivileged — no `CAP_SYS_ADMIN`, no `privileged: true`, default `RuntimeDefault` seccomp." The first two are still true. **The third is wrong.** `RuntimeDefault` seccomp blocks the bwrap path, so we need `Unconfined` seccomp on the worker pod — which is a real PSA-restricted-policy violation and a meaningful capability relaxation, even if it's not as bad as full `privileged`.

A custom seccomp profile that allows only `unshare(CLONE_NEWUSER)` and the syscalls bwrap needs, while still blocking other dangerous syscalls, is the right long-term answer. The Docker project has discussed this (moby/moby#42441) but no upstream profile ships with the carve-out yet. We may want to ship our own `bifrost-sandbox-seccomp.json` and document its use.

## Implications for sub-project (4) Code Execution

1. **The sandbox child process inherits the worker pod's seccomp profile** — there is no way for a userspace tool to "downgrade" a syscall filter mid-process. So if we want the bwrap-launched user code to be filtered by a strict seccomp profile, that filter has to be the worker pod's profile (or applied via bwrap's own `--seccomp` flag from a permissive parent).
2. **The recipe in this doc is the working baseline** — start the implementation here, not from the bwrap README's classical example.
3. **Ship a custom seccomp profile** — `bifrost-sandbox-seccomp.json` that allows the bwrap path while still blocking dangerous syscalls (kexec, ptrace of other processes, etc.). This is preferable to `Unconfined`.
4. **Preflight check inside the worker** — `unshare -U /bin/true` and report failure clearly with platform-specific remediation links. Required before any sandbox execution can be dispatched.
5. **Document a per-platform deployment guide** — at least for the 8 platforms in the table above.
6. **Anthropic's `enableWeakerNestedSandbox`** mode is the documented escape hatch for environments where the strong sandbox can't be made to work. We should expose it as an org-level config knob behind an explicit security-tradeoff acknowledgement.

## Side-finding: worker containers run as root

Confirmed: `api/Dockerfile` and `api/Dockerfile.dev` have no `USER` directive. The worker process runs as UID 0 inside the container.

This is **not** what's blocking bwrap (the AppArmor/seccomp denial is independent of in-container UID), but it's a separate hardening gap. Adding a non-root `USER` would be appropriate for general defense-in-depth, but doesn't help or hurt the sandbox design. Track separately.

## References

- `anthropic-experimental/sandbox-runtime` (the wrapper we'd actually use)
- `containers/bubblewrap` README and issue tracker, especially #505 ("bubblewrap inside unprivileged docker")
- Ubuntu 23.10 / 24.04 AppArmor unprivileged-userns restriction announcement
- Bottlerocket discussion #3318 (user namespace support)
- moby/moby#42441 (reevaluate Docker seccomp default for clone/unshare)
- K8s 1.33 release blog (user namespaces enabled by default in pods, separate feature from this discussion)
- This doc's empirical test was run on Ubuntu 24.04.3 LTS / kernel 6.8.0-110-generic / Docker desktop on 2026-04-27
