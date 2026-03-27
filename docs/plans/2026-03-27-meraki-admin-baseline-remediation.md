# Meraki Admin Baseline Remediation

## Goal

Use the `Midtown Technology Group` Meraki organization as the operational
baseline for standard Midtown admin access and remediate selected missing
Midtown admins across other Meraki organizations.

For this pass, `eric@carbonpeaktech.com` is treated as a valid Midtown-related
admin and baseline exception.

## Baseline

Baseline organization:

- `Midtown Technology Group`

Standard admin set for this pass:

- `patrick@midtowntg.com`
- `steven@midtowntg.com`
- `trevor@midtowntg.com`
- `miles@midtowntg.com`
- `matt@midtowntg.com`
- `bfunk@midtowntg.com`
- `chris@midtowntg.com`
- `scott@midtowntg.com`

Observed baseline access shape for these admins:

- `orgAccess = full`
- no tag restrictions
- no network restrictions

## Workflows Added

Reusable Meraki workflows added for this operational pattern:

- `Meraki: Audit Admins Against Baseline Organization`
- `Meraki: Sync Admins From Baseline Organization`
- `Meraki: Remove Admin Across Organizations`

These workflows are intended to support standard add/change remediation based on
a known-good Meraki org rather than an inferred domain-wide heuristic. They now
also support explicit org exclusions for legacy or vendor-disabled orgs.

## Live Remediation Scope

The remediation pass targets all auditable Meraki organizations missing any of
the selected standard admins above.

Known non-remediated orgs due Meraki API `403` on unlicensed orgs:

- `Jacobson Hile Kight`
- `Cynthia L Hovey DDS`
- `Connected Healthcare Systems`

Known intentionally excluded org:

- `Taylor Computer Solutions`

Known excluded org list for future baseline runs:

- `Taylor Computer Solutions`
- `Jacobson Hile Kight`
- `Cynthia L Hovey DDS`
- `Connected Healthcare Systems`

## Outcome

Before remediation, the selected admin set had `238` missing placements across
the audited Meraki estate.

After remediation, the selected admin set is fully aligned across the active
Meraki orgs we intend to manage.

Remaining admin drift for the selected set exists only in explicitly excluded or
vendor-disabled orgs:

- intentionally excluded: `Taylor Computer Solutions`
- Meraki-disabled for non-payment:
  - `Jacobson Hile Kight`
  - `Cynthia L Hovey DDS`
  - `Connected Healthcare Systems`

## Follow-up Cleanup

Confirmed typo account cleanup:

- `tleuke@midtowntg.com` was removed across the active managed Meraki orgs via
  `Meraki: Remove Admin Across Organizations`

Broader Meraki hygiene work still remaining after the baseline remediation and
typo-account cleanup:

- review and remove legacy or vendor admins such as:
  - `stephen@bionic-cat.com`
  - `doug@techsupportindy.com`
  - `dawn@gethotboxpizza.com`
- review intentional extra Midtown admins not present in the baseline org, such
  as:
  - `mgarcia@midtowntg.com`
  - `regina@midtowntg.com`
  - `kmiller@midtowntg.com`
- decide whether the broader baseline should also include additional Midtown
  staff currently missing from many orgs, especially:
  - `koerner@midtowntg.com`
  - `adam@midtowntg.com`
  - `mike@midtowntg.com`
  - `doug@midtowntg.com`
  - `tim@midtowntg.com`

## Team Note

This change standardizes the selected Midtown Meraki admin accounts by copying
their baseline access model from the `Midtown Technology Group` org into other
Meraki orgs where they were missing. The intent is to reduce admin drift and
make future Meraki admin additions or changes repeatable from a single baseline.
