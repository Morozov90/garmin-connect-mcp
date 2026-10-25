# Garmin Personal API capability verification

Checked on 2026-10-24 against official documentation, the published OpenAPI embedded
in Garmin's Swagger page, and the installed `garmin-connect-personal-api-python==1.0.0`.
Initial documentation/source verification used no live Garmin account requests.
Subsequent local verification on 2026-10-24 succeeded for all five tools; live
Codex activity and sleep queries also succeeded. Status 2 below
still applies to optional fields, device/sport coverage and historical availability
beyond those specific checks. Claude Code integration remains unverified.

Status vocabulary:
1. **Confirmed by official documentation or source.**
2. **Implemented but requires live account verification.**
3. **Unsupported or unavailable.** Where only documentation is missing, this means
   unavailable in this implementation, not a claim that Garmin will never offer it.

| Capability | Status | Evidence and limits |
| --- | --- | --- |
| Personal key creation/expiration/revocation | 1 | Garmin FAQ: creation in Connect; 30/90/180 days or one year; deleting a key revokes associated tokens. |
| Key exchange and token expiry | 1 | POST token endpoint; `ApiKey` authorization; bearer token valid up to 24 hours or key expiry, whichever is sooner. No refresh token. |
| Official SDK token cache/renewal | 1 | `PersonalApiAuthenticator.obtain_token`; cache fingerprint includes origin/key; renews with <=1 hour remaining. SDK does not automatically retry a stale-token 401. |
| Safe local key setup and cache coordination | 2 | Hidden terminal prompt, mode 700 directory/600 files, file lock and atomic replacement. Synthetic tests pass; actual local setup remains to be run. |
| Activity search with dates/sport/pagination | 2 | Official `search_activities(start,limit,start_date,end_date,activity_type)`; array of `SummarizedActivityDTO`. Parent sport types only. Date bounds inclusive in activity-local time. No maximum page size stated in Swagger; server limits 100 plus one lookahead. |
| Activity identifiers, duration, distance, speed, HR, power | 2 | `SummarizedActivityDTO` and `ActivitySummaryDTO.summaryDTO`. SI units documented; optional sport/device fields are not guaranteed. |
| Activity detail and split summaries | 2 | `get_activity(activity_id)`; `splitSummaries` are `SplitSummaryDTO` with `splitType` and `noOfSplits`. They can aggregate splits; individual laps are not guaranteed. |
| Per-activity training load/effect | 2 | `activityTrainingLoad`, `aerobicTrainingEffect` (search) / `trainingEffect` (detail), `anaerobicTrainingEffect`. These are reported activity values, not daily/acute/chronic load or readiness. |
| Recovery heart rate | 2 | Detail `summaryDTO.recoveryHeartRate`, bpm. This is a reported heart rate, not recovery time or a readiness assessment. |
| Sleep range/duration/stages/scores/times | 2 | `get_daily_sleep_summaries`; response is an array of `DailySleepDTO` (not an unofficial `dailySleepDTO` envelope). Official maximum 31 days. Score components are a map of `SleepScoreItem`, projecting numeric `value` only. |
| HRV daily summaries/baseline/status | 2 | `get_daily_hrv_summaries`; response is `{hrvSummaries:[HrvSummaryDTO]}`. Optional baseline/status retained. No range maximum or value units stated in Swagger; local maximum 31 days, values kept on Garmin's scale. |
| Steps, resting-HR field, stress, Body Battery | 2 | `get_daily_summaries` returns `{data:[UserDailySummaryV2DTO]}`. Read nested `movement.steps.value`, `heartRate.restingValue`, `stress.avgLevel`, `bodyBattery` values. Swagger allows up to one year; local maximum 31 days. `restingValue` may fall back to absolute minimum HR: do not treat it as guaranteed measured resting HR. |
| Separate steps/stress/Body Battery wrappers | 1 | Official SDK has them; documented maxima 28 days for steps/stress, 31 days for Body Battery. V1 uses nested daily summaries instead, avoiding extra calls. |
| Activity ZIP/FIT download | 1 | Official `download_activity` returns original ZIP bytes. Not exposed by this MCP. |
| Individual lap series, JSON samples/GPS tracks | 3 | No corresponding JSON endpoint found in the published Personal API paths. FIT parsing would require a separate design/dependency; v1 rejects sample/GPS flags. Start/end coordinates are omitted as well. |
| Daily training readiness, training status, acute/chronic load, recovery time | 3 | No dedicated endpoints found in the published Personal API. Never substituted with activity load, HRV or Body Battery. |
| Retention/backfill guarantee | 3 | No historical-retention guarantee found in the reviewed official pages/schema. Date filters do not prove that all past dates are accessible. Check your account. |
| Account/device-specific data availability | 2 | Depends on recorded/synced activities, firmware, wear time, account and sport. Device ownership alone does not prove any field will be returned. |
| Numeric API quotas/rate limits | 3 | No quota found in reviewed official sources. Implementation honors Retry-After, bounds GET retries, returns explicit rate-limit errors. |
| Sleep/HRV start-date versus wake-date meaning | 2 | Swagger describes calendarDate but does not settle night association. Values remain Garmin dates; compare sleep window timestamps during live verification. |
| Sleep timestamp representation | 2 | Swagger declares strings/date-time but describes GMT/local fields as “in ms.” Implementation accepts ISO date-time or numeric epoch milliseconds for GMT fields. Verify actual live format. |
| stdio discovery and five tool calls | 2 | Actual subprocess MCP smoke test passes using synthetic HTTP responses through the real official SDK; real client/account verification remains pending. |

## Official sources

- [Personal API overview and token exchange](https://developer.garmin.com/gc-developer-program/personal/personal-api)
- [Garmin Personal API FAQ](https://developer.garmin.com/gc-developer-program/personal/personal-faq/)
- [Garmin Personal API Swagger / OpenAPI](https://developer.garmin.com/gc-developer-program/personal/swagger-docs/)
- [Official Garmin Python client README](https://github.com/garmin/connect-personal-api-python)
- [Official client wrappers](https://github.com/garmin/connect-personal-api-python/blob/main/src/garmin_personal_api/client.py)
- [Official authenticator](https://github.com/garmin/connect-personal-api-python/blob/main/src/garmin_personal_api/auth.py)
- [Official Garmin PyPI package](https://pypi.org/project/garmin-connect-personal-api-python/1.0.0/)
- [Official MCP SDK v1.30.0](https://github.com/modelcontextprotocol/python-sdk/tree/v1.30.0)
- [MCP v2 migration: FastMCP renamed MCPServer](https://py.sdk.modelcontextprotocol.io/migration/)

The Swagger page embeds the OpenAPI JSON in its JavaScript bundle; that specification,
not inferred Garmin Connect web endpoints, was used to verify the nested response shapes.
No schema or fixture is a live-account capture.
