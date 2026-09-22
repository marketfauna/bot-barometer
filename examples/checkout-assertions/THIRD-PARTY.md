# Source and license attribution

The demonstration application is [Sauce Labs sample-app-web](https://github.com/saucelabs/sample-app-web), offered under its [MIT license](https://github.com/saucelabs/sample-app-web/blob/e0948dd03f0042ad24f5e9ca324657f13193c19f/LICENSE). The exact deployed build and file hashes are in inputs.json. The license is fetched unchanged beside the local sample.

The public release contains our example code and a pinned download manifest, not the upstream compiled bundles. fetch-inputs.cjs retrieves the upstream files directly and preserves their bytes, including any embedded notices. Do not strip notices from downloaded files. The deployed upstream tree had no separate license/notice files; its source license is recorded separately. This is provenance, not a full audit of the compiled application's dependencies.

[Playwright](https://github.com/microsoft/playwright) is an external dependency licensed under [Apache 2.0](https://github.com/microsoft/playwright/blob/main/LICENSE); no Playwright or browser binary is included. The MIT license here applies to the Marketfauna example files, not third-party dependencies. Sauce Labs and Microsoft do not sponsor or endorse this example.
