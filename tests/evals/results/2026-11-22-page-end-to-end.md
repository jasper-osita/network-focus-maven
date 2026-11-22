# Installed page, end to end with real Claude — 2026-11-22

Fresh install of the page (`install_app.py`, Mac layout) on a clean machine, the real roster in the inbox, real `claude -p` with the page's own background permission rules. Script: driven through the page's HTTP API exactly as the buttons do.

| Step | Result |
|---|---|
| Generate | **done in 134 s.** Steps shown: Checking the data → Reviewing Goal 1/2/3 → Fact-checking the picks → Making the PDF. #1 Diana Chen; also Marcus Wei, Paul Christiano, Sarah Guo, David Park; dormant Reid Hoffman, Priya Mehta; 7 questions; goal rings 4 / 2 / 2. |
| Roster changed (Ana Ruiz, a16z, Series C call request added) | "Roster updated · New: Ana Ruiz" appeared within seconds (check interval shortened for the test). |
| Update | **done in 55 s.** Ana Ruiz placed with the New chip, in place of David Park (weakest open pick; Diana still covers the CTO goal). David Park moved to Worth considering. #1 unchanged. The roster line cleared afterwards. |

Not covered here: launchd start on a real Mac (fixed in 0.3.1: re-install now waits for the old page to stop), Google Drive for desktop access, Windows.
