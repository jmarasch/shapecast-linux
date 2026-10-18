# Queue and job visibility

In native mode, choose **Manage jobs** in the top toolbar.

- **Clear waiting queue (N)** asks you to confirm cancellation of the waiting jobs in the displayed snapshot. A job that already started is skipped. Jobs added after that snapshot are not included. Running jobs and casts waiting for selection, alternate-view approval or rig approval stay unchanged.
- **Cancel waiting job** cancels one job that has not started. If it started while the panel was open, the action is rejected; use the original cast controls to stop active work.
- **Hide** unlists a completed, failed or cancelled job from the original job history and queue recents. Active and approval-paused jobs cannot be hidden here.
- **Show hidden jobs** displays a separate list with **Restore to lists** controls. Hidden state survives a refresh or restart. This checkbox shows hidden jobs only.
- **Refresh**, **Previous** and **Next** let you browse the complete history, including histories longer than 50 jobs. Close the panel after changes to refresh the original application's lists too.

These controls do not delete job records, work files, generated models, exports or library assets. Cancelled jobs remain in history until you hide them. Hiding a job does not remove its asset from the library or prevent opening its detail directly. Cancellation does not automatically requeue work; use the vendor's retry controls when appropriate.

The helper stores one visibility marker in job parameters; it makes no database schema changes and leaves the commercial files unchanged. The original cancellation service records cancellation and preserves completed steps. A process-local lock serializes queue admission with cleanup. Clearing is snapshot based and can report skipped jobs if their state changed. Interrupted cleanup may have cancelled part of the snapshot; refresh before trying again.

All control routes require the normal per-session bearer token. A fixed-scope, same-origin loopback relay handles the browser connection; it cannot forward arbitrary URLs or other core routes. Licence and generation permissions are unchanged.

Validation covers a disposable original-core database with 61 synthetic jobs, a longer hidden history, preservation of every work file, restart/restore, queue admission locking, and authenticated API access. Browser checks cover clear confirmation, preservation of running/approval jobs, hide/restore, pagination and reloading the original UI. No existing owner jobs are cleared or hidden by these tests.
