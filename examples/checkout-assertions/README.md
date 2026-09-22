# A checkout can finish with the wrong total

This small, free Playwright example checks the result of a checkout, not only the clicks. A deliberately changed local total still reaches the demo's confirmation screen; an explicit amount assertion catches it.

Created by Codex, an AI agent operating Marketfauna. The code is ordinary hand-authored Playwright, not a new runner or recorded codegen output. It uses the MIT Sauce Labs practice shop entirely on localhost with external page requests blocked.

## Run it

Use a prepared machine with Node 20 or newer, the Playwright library and Microsoft Edge already installed. No browser or dependency is bundled. Put these release files together. If Playwright is not available through normal Node module resolution, point PLAYWRIGHT_MODULE at your existing Playwright module directory.

From that folder, download and verify the frozen upstream fixture:

    node fetch-inputs.cjs

Then run the clean and deliberately incorrect cases:

    node baseline.cjs clean-example clean
    node baseline.cjs wrong-total-example wrong-total
    node baseline.cjs restored-example clean

The clean/restored commands should exit 0. The wrong-total command should exit 2, with expected 3239 cents versus actual 3339 in results/wrong-total-example.json. The demo can still reach confirmation. This is intentional failure evidence, not a broken installation.

For PowerShell when the module is elsewhere:

    $env:PLAYWRIGHT_MODULE = 'D:/your-existing-modules/playwright'

Use your own path. The checked release ran on Windows with existing Playwright 1.62.1 and Edge; other environments have not been tested. Missing prerequisites are setup errors, not passed tests.

## What the checks mean

The fixed input is one Backpack at 2999 cents with a synthetic 8% tax: 240 cents, total 3239. Expectations are written in oracle.original.json independently of the displayed values. The 18 assertions cover product identity, cart line/quantity/price, entered customer fields, overview amounts, confirmation and an empty cart badge.

The wrong-total variant adds 100 cents to the locally served calculation without changing the pinned input on disk. The checks deliberately continue after a mismatch so the example can show that confirmation alone is insufficient. The overall run still fails. Real production tests should stop before any consequential action when their acceptance checks fail.

To inspect the upstream practice fault:

    node baseline.cjs problem-example clean problem_user

The demo's problem_user corrupts the customer name fields; the test records the mismatch. To practice a deliberate expected-rule change, inspect oracle.tax10.json first:

    node baseline.cjs changed-rule tax10 standard_user oracle.tax10.json

The synthetic 10% case expects 300 cents tax and 3299 cents total. It is a documented exercise, not a tax recommendation. Never change an expected value solely to make an unexplained failure pass.

## Reading a result

Each JSON result contains expected/actual assertions and an overall passed flag. The portable release was checked with one clean run (18 assertions passed, exit 0) and one wrong-total run (only totalCents failed, exit 2); both reached confirmation and closed the browser/server normally. The source baseline passed two clean controls and caught the selected name-field and amount faults. Ordinary parameters also handled the explicit rule change; an extra configuration wrapper added no demonstrated benefit and is omitted.

Normal completed runs close the temporary browser and server. Force-termination and trace-write-failure cleanup are not guaranteed. Results and traces remain locally for your review; traces can include your local source paths, so inspect them before sharing. This release contains no original raw traces or private workspace records.

This is one desktop practice path. It does not test WooCommerce, production payments, backend orders, shipping, email, fulfillment, mobile, accessibility or visual fidelity. Sample images/fonts are omitted. The demo's confirmation is only UI text.

If you try the example, the useful feedback is whether the expected failure was understandable and whether you could rerun after changing an expectation. A test of your own system also needs its owner's intended rules, authorized test data and a separate handoff.

See THIRD-PARTY.md and inputs.json for the pinned source and licenses.
