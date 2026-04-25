param(
    [string]$Repo = "jackmusick/bifrost",
    [int]$Limit = 20,
    [int]$Pr,
    [switch]$Json
)

$ErrorActionPreference = "Stop"

function Invoke-GhJson {
    param([string[]]$Arguments)

    $output = & gh @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "gh $($Arguments -join ' ') failed: $output"
    }

    if ([string]::IsNullOrWhiteSpace($output)) {
        return $null
    }

    return $output | ConvertFrom-Json
}

function Get-CheckSummary {
    param([int]$Number)

    $lines = & gh pr checks $Number --repo $Repo --watch=false 2>&1
    if ($LASTEXITCODE -ne 0 -and ($null -eq $lines -or $lines.Count -eq 0)) {
        return [pscustomobject]@{
            failed = 0
            pending = 0
            passed = 0
            unknown = 1
            failingChecks = @("Unable to read checks.")
        }
    }

    $failed = @()
    $pending = 0
    $passed = 0
    $parsed = 0
    foreach ($line in $lines) {
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }

        $parts = $line -split "`t"
        if ($parts.Count -lt 2) {
            continue
        }

        $parsed += 1
        $name = $parts[0]
        $state = $parts[1]
        switch ($state) {
            "fail" { $failed += $name }
            "pass" { $passed += 1 }
            "pending" { $pending += 1 }
            "queued" { $pending += 1 }
            "in_progress" { $pending += 1 }
        }
    }

    if ($parsed -eq 0 -and $LASTEXITCODE -ne 0) {
        return [pscustomobject]@{
            failed = 0
            pending = 0
            passed = 0
            unknown = 1
            failingChecks = @("Unable to parse checks: $lines")
        }
    }

    [pscustomobject]@{
        failed = $failed.Count
        pending = $pending
        passed = $passed
        unknown = 0
        failingChecks = $failed
    }
}

function Get-ReviewThreadSummary {
    param([int]$Number)

    $query = @'
query($owner:String!, $name:String!, $number:Int!) {
  repository(owner:$owner, name:$name) {
    pullRequest(number:$number) {
      reviewThreads(first:100) {
        nodes {
          isResolved
        }
      }
    }
  }
}
'@

    $repoParts = $Repo -split "/", 2
    try {
        $result = Invoke-GhJson @(
            "api", "graphql",
            "-f", "query=$query",
            "-F", "owner=$($repoParts[0])",
            "-F", "name=$($repoParts[1])",
            "-F", "number=$Number"
        )
    }
    catch {
        return [pscustomobject]@{
            unresolved = 0
            total = 0
            readable = $false
        }
    }

    $threads = @($result.data.repository.pullRequest.reviewThreads.nodes)
    [pscustomobject]@{
        unresolved = @($threads | Where-Object { -not $_.isResolved }).Count
        total = $threads.Count
        readable = $true
    }
}

function Get-NextAction {
    param(
        [object]$PullRequest,
        [object]$Checks,
        [object]$Threads
    )

    if ($PullRequest.isDraft) {
        return "Draft: leave unmerged; fix checks and update PR summary before marking ready."
    }

    if ($PullRequest.mergeStateStatus -eq "BEHIND") {
        return "Update branch from main in an isolated worktree, then rerun checks."
    }

    if ($Checks.failed -gt 0) {
        return "Fix failing checks: $($Checks.failingChecks -join ', ')."
    }

    if ($Threads.unresolved -gt 0) {
        return "Address or reply to $($Threads.unresolved) unresolved review thread(s)."
    }

    if ($PullRequest.mergeStateStatus -eq "BLOCKED") {
        return "Blocked with no readable failing check; inspect branch protection and required reviews."
    }

    if ($PullRequest.mergeStateStatus -eq "CLEAN" -or $PullRequest.mergeStateStatus -eq "HAS_HOOKS") {
        return "Green candidate: human reviews policy; agent may enable auto-merge only if lane is allowed."
    }

    return "Inspect manually: merge state is $($PullRequest.mergeStateStatus)."
}

$fields = "number,title,state,isDraft,mergeStateStatus,reviewDecision,headRefName,baseRefName,author,labels,updatedAt,url"
if ($Pr -gt 0) {
    $pullRequests = @(Invoke-GhJson @("pr", "view", "$Pr", "--repo", $Repo, "--json", $fields))
}
else {
    $pullRequests = @(Invoke-GhJson @("pr", "list", "--repo", $Repo, "--limit", "$Limit", "--json", $fields))
}

$queue = foreach ($pullRequest in $pullRequests) {
    $checks = Get-CheckSummary -Number $pullRequest.number
    $threads = Get-ReviewThreadSummary -Number $pullRequest.number
    $labels = @($pullRequest.labels | ForEach-Object { $_.name })

    [pscustomobject]@{
        number = $pullRequest.number
        title = $pullRequest.title
        url = $pullRequest.url
        author = $pullRequest.author.login
        branch = $pullRequest.headRefName
        draft = [bool]$pullRequest.isDraft
        mergeState = $pullRequest.mergeStateStatus
        reviewDecision = $pullRequest.reviewDecision
        labels = $labels
        checks = $checks
        reviewThreads = $threads
        nextAction = Get-NextAction -PullRequest $pullRequest -Checks $checks -Threads $threads
    }
}

if ($Json) {
    $queue | ConvertTo-Json -Depth 10
    exit 0
}

"# PR Steward Queue"
""
"Repository: $Repo"
"Generated: $((Get-Date).ToString("s"))"
""
foreach ($item in $queue) {
    "## #$($item.number) $($item.title)"
    "- State: merge=$($item.mergeState); draft=$($item.draft); review=$($item.reviewDecision)"
    "- Branch: $($item.branch)"
    "- Checks: passed=$($item.checks.passed); failed=$($item.checks.failed); pending=$($item.checks.pending)"
    if ($item.checks.failingChecks.Count -gt 0) {
        "- Failing checks: $($item.checks.failingChecks -join ', ')"
    }
    "- Review threads: unresolved=$($item.reviewThreads.unresolved); total=$($item.reviewThreads.total)"
    "- Next action: $($item.nextAction)"
    "- URL: $($item.url)"
    ""
}
