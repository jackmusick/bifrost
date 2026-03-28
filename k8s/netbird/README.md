## NetBird on k3s

This directory holds the repo-backed configuration for the initial NetBird
operator rollout on the Bifrost k3s cluster.

Scope of the first pass:
- install the NetBird Kubernetes operator
- expose the Kubernetes API privately to the NetBird mesh
- prepare the cluster for private service exposure later

Deliberate non-goals for the first pass:
- public reverse proxy exposure
- Gateway API beta usage
- broad service annotation rollout

Operational note:
- the initial policy uses the NetBird `All` group as the source group so remote
  access works immediately for existing peers
- tighten this later once a dedicated admin peer/group exists

Current remote-access notes:
- the stable remote browser path is the NetBird reverse-proxy URL for Bifrost UI
- the stable remote CLI path is the NetBird reverse-proxy URL for the dedicated
  host-backed API proxy
- the private lab-subnet ingress VIP path (`10.1.23.240` / `10.1.23.114:443`)
  is not currently the primary remote path because subnet-routed HTTPS to the
  ingress VIP does not reliably answer from remote NetBird peers
- see [2026-03-28-netbird-remote-access-architecture.md](/home/thomas/mtg-bifrost/bifrost/docs/plans/2026-03-28-netbird-remote-access-architecture.md)
  for the current architecture, stateful host changes, and cleanup plan
