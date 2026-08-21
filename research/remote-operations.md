# Remote Operations MVP

The Operations page is the private, read-mostly surface for supervising unattended Pokemon Player work. It deliberately does not expose the broader lab, raw model requests, ROM/save paths, credentials, or arbitrary local files.

## Start and stop

From the project root:

```powershell
.\scripts\operations.ps1 -Action Start
```

The launcher starts the sanitized Operations service, a production build of the phone-oriented UI, and the Director sidecar when the local ROM is present. Every service binds to the local machine only. It also configures Tailscale Serve when Tailscale is installed and the current Windows session has permission to manage it.

Useful launcher actions:

```powershell
.\scripts\operations.ps1 -Action Status
.\scripts\operations.ps1 -Action Stop
.\scripts\operations.ps1 -Action StartAcceptance
```

`StartAcceptance` launches a slow, ROM-free fixture that behaves like an active bounded run. Its default window is one hour, leaving time to switch devices and test disconnect behavior. It is safe to pause, resume, stop after an action, or emergency-stop while testing the phone workflow.

## Private phone access

1. Install Tailscale on the development computer and phone.
2. Sign both devices into the same private tailnet.
3. Run the Operations launcher.
4. Read the private HTTPS address shown by `tailscale serve status` on the computer and open it on the phone.

Tailscale Serve proxies the loopback-only Operations UI to authenticated devices in the private tailnet. Do not use public Funnel access for this project.

On Windows, the host package can be installed with `winget install --id Tailscale.Tailscale --exact`. The Tailscale sign-in itself is intentionally left to the operator; the project never stores or handles tailnet credentials.

Tailscale Serve configuration persists independently of the local UI process. On Windows, run the following once from an Administrator PowerShell if the ordinary launcher reports that Tailscale Serve could not be configured:

```powershell
tailscale serve --bg http://127.0.0.1:3000
tailscale set --unattended=true
```

Unattended mode keeps the private network connection available after the interactive Windows user logs out. The Operations service and UI still need to be running; Tailscale does not start or own the project processes.

The launcher enables remote-only mode for the UI. In that mode only `/operations`, `/api/operations`, restricted run artifacts, and required UI assets are reachable; the general research lab and raw Director endpoints return `404`.

## Phone acceptance test

1. Start the acceptance fixture with `.\scripts\operations.ps1 -Action StartAcceptance`.
2. Open the private Operations address on the phone.
3. Confirm the live card shows **Remote Operations Acceptance**, a changing action count, screenshot, party, inventory, Director decision, and latest result.
4. Tap **Pause**. Wait at least ten seconds and confirm the action count does not change.
5. Close the phone page for ten seconds, reopen it, and confirm the run is still paused. This proves client connection loss does not alter the local run.
6. Tap **Resume** and confirm the count advances.
7. Tap **Stop after action** and confirm the fixture reaches a durable checkpoint with a safe summary.
8. Confirm the Control audit lists each command.

The milestone's human acceptance burden is only this phone test. It does not need the ROM, LM Studio, Gemma, or a gameplay artifact.

### Acceptance record

Milestone 1 phone acceptance passed on 2026-08-20 using an authenticated iPhone over the private tailnet:

- The phone loaded the production Operations page and observed fixture `operations-test-20260821T014300Z`.
- **Pause** was accepted from `remote_operations_ui` at action 316. The count remained at 316 for more than three minutes while the phone page was closed, and the reopened page still showed the durable paused state.
- **Resume** was accepted from the phone and the count advanced.
- **Stop after action** was accepted from the phone and produced a safe checkpoint at action 399 with verdict `healthy_needs_review`, `continueRecommended=false`, and stop reason `operator_stop_after_action`.
- The final private-route audit exposed the Operations page, API, and restricted artifacts while returning `404` for the Director, states, local-image, and lab routes. The parsed public payload contained no credential fields, ROM paths, raw model payloads, or unrestricted filesystem paths.

## Control semantics

- **Pause** waits between bounded semantic actions. It never interrupts an emulator input sequence halfway through.
- **Resume** clears pause and any queued stop-after-action request.
- **Stop after action** lets the current bounded action finish and then saves a checkpoint.
- **Emergency stop** prevents the next action from starting and saves at the earliest safe action boundary.

Control state lives in a local durable file, not in the browser session. Closing the browser, losing phone service, or restarting the UI therefore does not resume, stop, or corrupt the run.

Raw emulator buttons are absent from Operations. The local Director lab exposes them only after explicitly entering Diagnostic Capture Mode, and the sidecar rejects raw input if that mode is not enabled.

## Dropbox status

The page reports whether a segment video exists in the configured local Dropbox folder and provides a playable private link when it does. It intentionally says “ready in Dropbox folder”; it does not claim cloud upload completion because that remains the Dropbox desktop client's responsibility.
