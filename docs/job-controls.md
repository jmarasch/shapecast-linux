# Clear finished records on Queue

Open the original **Queue** page.

- **Clear all** clears completed, failed and cancelled records from the Finished list. It includes older finished records beyond the page's 25-row recent window, so they do not keep reappearing.
- Hover over a finished row to reveal a small **×** at its left. Click it to clear that one record. Keyboard focus also reveals the control; touch devices keep it visible.
- **Undo clear** restores the last cleared record or group. Undo is retained when navigating within the app or refreshing the same browser session.

Pending, running and approval-paused jobs are never cleared by these controls. Clearing a record does not cancel a job, delete a database record, remove generated files or exports, or unlist an asset from the library. Other job history remains available. Cleared Queue records stay cleared across app restarts.

The previous separate Manage jobs panel and its waiting-job cancellation controls were removed in helper 0.4.2. The original Queue button named Clear, which cancelled waiting jobs, is hidden to avoid confusing it with the new Clear all. The vendor's normal Pause, Resume, Retry and individual pending-job controls remain available.

Queue visibility uses a helper marker in job parameters, without a database schema change. Clearing runs as one conditional database update restricted to terminal statuses, so a concurrent retry or state change cannot clear active or pending work. Undo removes only the marker belonging to its own cleared group. Generation, licence permissions, work items and job statuses are unchanged.

The reviewed 0.3.17 UI bundle receives stable Queue-page and finished-row identifiers while being served. Its file on disk is unchanged. The adapter accepts only the reviewed bundle hash and does not guess job IDs from titles, list order or React internals. A future software version requires review before these controls can attach to its interface.

All routes require the original per-session bearer token. The browser uses a fixed-scope same-origin loopback relay. Compatibility routes retain restoration of legacy global-hidden jobs from helper 0.4.1; new Queue clearing does not hide jobs globally.

Private validation uses synthetic jobs in an isolated original-core profile, including more than 25 finished records, active work, pending work and both approval states. It checks file retention, unchanged statuses/parameters, Queue-only visibility, restart persistence, Undo and authentication. Browser checks use the original Queue page. No owner records are cleared during validation.
