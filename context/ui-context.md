# UI Context

> Visual and interaction reference for the operator page. Read it before you change `frontend/index.html`.
> Facts were read from the code (commit `eea63ab` plus the working tree of 2026-10-18) and checked by
> running the app in headless Chromium (desktop 1280 px, widths 900, 700 and 390 px). Line numbers refer to
> `frontend/index.html` (737 lines: `<style>` lines 8 to 202, body 205 to 357, `<script>` 359 to 735).
> Product goals are in `project-overview.md`. Routes, data and decision logic are in `architecture-context.md`.

## Principles

- **One page, for the plant operator.** `frontend/index.html` is the whole interface. Plain HTML, one `<style>`, one `<script>`. No framework, no build step.
- **Sections follow the operator's questions, in this order:** 1. Is it working, and what is it doing? (Right now) 2. What will it do, and why? (Tonight and tomorrow) 3. What is it saving, and which part is the software? (Savings) 4. What is my system? (Your system). A chat panel ("Ask your plant") sits outside this order.
- **One sentence says what the plant is doing.** It is `decision.reason` from `/api/live`, shown big, next to the flow diagram. The backend guarantees it matches the power flow.
- **Honest numbers.** Savings are shown as layers. Only the violet layer, "myEnergy's planning", is what the software adds. Savings are labelled "estimated" and come from a simulated month.
- **Colour always means the same thing** (comment at the top of the `<style>`, line 9).
- **Plant-local time everywhere.** Times come from the API's `label` strings or are formatted in the plant's time zone. Exceptions are listed in Known UI Facts.
- **Read-only.** Nothing on the page changes the plant. The only write is the chat question (`POST /api/ask`).
- **Motion is decoration** (comment at line 197). People who ask for less motion get a still page.

## Theme

Dark only. There is no `prefers-color-scheme` rule, no `color-scheme` meta and no light variables.

**Colour meaning:**

| Colour | Variable | Means |
|--------|----------|-------|
| amber | `--sun` | sun, solar power |
| green | `--battery` | battery (also the brand accent and the "ok" state) |
| coral | `--grid` | grid (also the "bad" state) |
| blue | `--cheap` | cheap-rate hours |
| violet | `--plan` | what myEnergy's planning adds |

**Every `:root` variable (lines 12 to 18):**

| Role | CSS variable | Value |
|------|--------------|-------|
| Page background | `--bg` | `#07080A` |
| Card background | `--card` | `#101216` |
| Inner surface (tiles, price box, layer rows, chips, inputs) | `--card2` | `#15181D` |
| Borders, flow tracks, grid lines | `--border` | `#22262D` |
| Main text | `--text` | `#F2F4F7` |
| Secondary text | `--muted` | `#8C95A4` |
| Weak text (sub-labels, footnotes, footer) | `--faint` | `#5E6674` |
| Sun / solar | `--sun` | `#FFB72B` |
| Battery | `--battery` | `#15E6A0` |
| Grid | `--grid` | `#FF5A72` |
| Cheap hours | `--cheap` | `#378ADD` |
| myEnergy's planning | `--plan` | `#A18BFF` |
| State: ok (pill dot) | `--ok` | `#15E6A0` (same as `--battery`) |
| State: warning (pill, notice, chat error) | `--warn` | `#FFB72B` (same as `--sun`) |
| State: bad (pill) | `--bad` | `#FF5A72` (same as `--grid`) |
| Card radius | `--r-card` | `18px` |
| Standard gap (story, KPI grid) | `--gap` | `14px` |

`--cheap` is defined but never read with `var(--cheap)`. The cheap colour is hard-coded as `rgba(55,138,221,...)` and `#7FB6EE` (below).

### Colors outside the tokens

| Colour | Where | Role |
|--------|-------|------|
| `rgba(21,230,160,0.07)` at `85% -120px`, 900 x 420 px; `rgba(255,183,43,0.05)` at `-10% 10%`, 700 x 380 px | `body` `background-image` (two radial gradients, no-repeat) | faint green and amber glow in the page corners |
| `rgba(7,8,10,0.78)` + `blur(12px)` | `header` background | `--bg` at 78 %, glass effect |
| `rgba(21,230,160,0.55)` to `rgba(21,230,160,0)` | `@keyframes beat` | pulse ring of the ok dot and the running-device dot |
| `rgba(255,183,43,0.35)` | `.notice.warn` border | warning notice |
| `#3A404A` | `.n-load .ic` border | factory node ring (always on) |
| `rgba(255,183,43,0.6)`, ring `0.08`, glow `0.25` (28 px) | `.n-solar.on .ic` | solar node glow |
| `rgba(21,230,160,0.6)`, ring `0.08` | `.n-batt.on .ic` | battery node ring |
| `rgba(255,90,114,0.6)`, ring `0.08` | `.n-grid.on .ic` | grid node ring |
| `rgba(55,138,221,0.18)` bg + `#7FB6EE` text | `.tag.cheap` | "cheap hour" tag |
| `rgba(140,149,164,0.16)` bg + `var(--muted)` | `.tag.std` | "average hour" tag |
| `rgba(255,90,114,0.15)` bg + `var(--grid)` | `.tag.dear` | "expensive hour" tag |
| `rgba(21,230,160,0.12)` bg + `var(--battery)` | `.tone-sun .story-ic` | story icon, tone sun |
| `rgba(255,183,43,0.12)` bg + `var(--sun)` | `.tone-buy .story-ic` | story icon, tone buy |
| `#C7CDD6` | `#story-detail` text; `#fl-load` stroke; chart "now" line and text | light grey: story text, factory flow, "now" marker |
| `rgba(255,255,255,0.04)` | `.seg button[aria-selected="true"]` shadow | 1 px top highlight |
| `rgba(161,139,255,0.10)` bg, `rgba(161,139,255,0.35)` border | `.layers li.mine` | violet "myEnergy's planning" row |
| `#2A2F37` | `#b-bill` (stack segment) and the "Still paid" marker (inline `style`) | dark grey: the bill still paid |
| `rgba(55,138,221,0.45)` | legend swatch "Cheapest hours" (inline `style`) | the chart band itself is drawn at `0.11` |
| `rgba(21,230,160,0.4)` | `.ask-btn` border | chat button |
| `rgba(0,0,0,0.45)` / `rgba(0,0,0,0.55)` | `.ask-btn` / `.ask-panel` box-shadow | `0 6px 24px` / `0 12px 40px` |
| `rgba(21,230,160,0.14)` | `.msg.me` background | own chat messages |
| `#04110B` | `.ask-form button` text | dark text on the green Send button |
| `#FFB72B`, `#FF5A72`, `#15E6A0`, `#C7CDD6` | `stroke` attributes of `#fl-solar`, `#fl-grid`, `#fl-batt`, `#fl-load` | flow lines (SVG attributes cannot use `var()` here) |
| chart: `#FF5A72` / `rgba(255,90,114,0.45)`, `#FFB72B` / `rgba(255,183,43,0.15)`, `#8C95A4`, `#15E6A0`, tick colour `#8C95A4`, grid `rgba(255,255,255,0.06)`, band `rgba(55,138,221,0.11)` | chart setup (`drawChart`, `cheapBands`) | canvas cannot read CSS variables; these repeat `--grid`, `--sun`, `--muted`, `--battery` |

Contrast (computed on the real colours): `--text` on `--card` 17.0:1; `--muted` on `--card` 6.2:1; `--muted` on `--card2` 5.9:1; `#C7CDD6` on `--card` 11.7:1; `--faint` on `--card` 3.2:1, on `--card2` 3.1:1, on `--bg` 3.5:1.

## Typography

- Font stack: `-apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', Roboto, Helvetica, Arial, sans-serif`. No web font is loaded. `Inter` is used only if installed. Buttons and inputs use `font: inherit`.
- Base: `15px`, line height `1.5`, `-webkit-font-smoothing: antialiased`.
- The chart text is not set by the page. Chart.js defaults apply (`'Helvetica Neue', Helvetica, Arial, sans-serif`, 12 px). Only the "now" label is set (`12px -apple-system, Inter, sans-serif`).
- Numbers use `font-variant-numeric: tabular-nums` on: `.node .v`, `.price b`, `.share b`, `.tile .v`, `.big`, `.sv-top .v`, `.layers em`.

| Element | Selector | Size | Weight | Other |
|---------|----------|-----:|-------:|-------|
| Logo | `.logo` | 18 | 800 | letter-spacing -0.4px; "Energy" in `--battery` |
| Plant name / location | `.plant` / `.plant b` | 14 | 400 / 600 | `--muted` / `--text` |
| Nav links | `.nav a` | 13.5 | 600 | `--muted`; hover and `.active`: `--text` on `--card2` |
| Status pill | `.pill` | 13 | 600 | |
| Section heading | `h2` | 18 | 700 | letter-spacing -0.2px |
| Section meta | `.meta` | 12.5 | 400 | `--muted` |
| Eyebrow | `.eyebrow` | 12 | 700 | uppercase, letter-spacing .06em, `--muted` |
| Hub label | `.hub-label` | 11 | 700 | uppercase, letter-spacing .05em, `--muted` |
| Node name | `.node .nm` | 12 | 600 | `--muted`, margin-top 7px |
| Node value | `.node .v` | 21 | 800 | letter-spacing -0.5px, line height 1.2 (17 px at 540 px and below) |
| Node sub-text | `.node .s` | 12 | 400 | `--faint`, line height 1.35 |
| The sentence | `.side .sentence` | 21 | 700 | letter-spacing -0.3px, line height 1.35 (18 px at 540 px and below) |
| Price | `.price b` | 20 | 800 | |
| Price tag | `.price .tag` | 11.5 | 700 | |
| Price helper | `.price span.s` | 12.5 | 400 | `--muted` |
| Solar share row | `.share` | 13 | 400 | `--muted`; value `b` in `--text` |
| Story headline | `#story-headline` | 20 | 700 | letter-spacing -0.2px |
| Story detail | `#story-detail` | 15 | 400 | `#C7CDD6`, line height 1.6 |
| Notice | `.notice` | 15 | 400 | `--muted`, line height 1.6 |
| KPI label / value / sub | `.tile .l` / `.v` / `.s` | 12.5 / 26 / 12.5 | 600 / 800 / 400 | value letter-spacing -0.6px; sub `--faint` |
| Legend | `.legend span` | 12 | 400 | `--muted` |
| Segmented control | `.seg button` | 13 | 600 | |
| Savings total | `.big` | 34 | 800 | letter-spacing -1px, line height 1.15 (28 px at 540 px and below) |
| CO2 value | `.sv-top .v` | 22 | 800 | |
| Savings label / sub | `.sv-top .l` / `.s` | 12.5 | 600 / 400 | `--muted` / `--faint` |
| Layer title / text / amount | `.layers b` / `span` / `em` | 14 / 12.5 / 16 | 700 / 400 / 800 | text line height 1.45; amount `white-space: nowrap`, not italic |
| Footnote | `.foot` | 12 | 400 | `--faint`, line height 1.5 |
| Facts term / value | `.facts dt` / `dd` | 13.5 / 14 | 400 / 500 | `--muted` / `--text` |
| Device status | `.dev .st` | 13 | 400 | `--muted`, block |
| Footer | `footer` | 12.5 | 400 | `--faint`; links `--muted` |
| Chat button | `.ask-btn` | 14 | 600 | |
| Chat title / message / chip | `.ask-head h2` / `.msg` / `.ask-chips button` | 16 / 14 / 12.5 | 700 / 400 / 400 | message line height 1.5 |
| Chat input / Send | `.ask-form input` / `button` | 14 / 14 | 400 / 600 | input is 16 px at 540 px and below |

## Spacing, Radius and Layout

- Reset: `*{box-sizing:border-box;margin:0;padding:0}`. `html{scroll-behavior:smooth}`.
- **`.wrap`:** `max-width: 1120px`, centred, side padding `20px`. It is used on the header bar, on `<main>` and in the footer. The gutter never changes with width.
- **Header:** `position: sticky; top: 0; z-index: 10`, `border-bottom: 1px solid var(--border)`. `.bar` is a flex row, `gap: 18px`, `min-height: 62px`, `flex-wrap: wrap`, 8 px top and bottom. The brand has `margin-right: auto`, so the nav and the pill sit on the right. Measured height: 63 px.
- `main` has `padding-top: 26px`. `section` has `margin-bottom: 38px` and `scroll-margin-top: 80px` (the sticky header does not cover an anchor target). `.sec-head` is a flex row (`space-between`, `align-items: baseline`, `gap: 10px`, wraps), `margin-bottom: 12px`.
- **`.card`:** `--card` background, `1px solid var(--border)`, radius `var(--r-card)`, padding `20px 22px`.
- **Footer:** `margin-top: 38px`, `padding: 18px 0 90px` (the 90 px keeps the page end clear of the floating chat button), `border-top`.
- **z-index:** header 10, chat button 20, chat panel 21.
- **`.hero`** (the "Right now" card): grid `minmax(0,1.35fr) minmax(0,1fr)`, `gap: 26px`, `align-items: center`. Left: the flow diagram. Right: `.side`.
- **`.flow`:** `aspect-ratio: 4/3`, `width: 100%`, `max-width: 560px`, centred. The SVG fills it (`viewBox 0 0 400 300`). At 1280 px it measures 560 x 420.
- **`.cols`** (Savings and Your system): grid `minmax(0,1.25fr) minmax(0,1fr)`, `gap: 24px`, `align-items: start`. Sections inside it have `margin-bottom: 0`.
- **`.kpis`:** `repeat(auto-fit, minmax(180px, 1fr))`, `gap: var(--gap)`. Three tiles sit in one row when the card is at least about 612 px wide, then two columns, then one.
- **Radius scale in use:**

| Radius | Used on |
|-------:|---------|
| 18px (`--r-card`) | `.card`, `.ask-panel` |
| 16px 16px 0 0 | `.ask-panel` at 540 px and below |
| 14px | `.price`, `.tile` |
| 12px | `.layers li`, `.msg` |
| 10px | chat input, Send button |
| 8px | `.ask-close` |
| 4px / 3px / 2px / 1px | `.batt-ic` / layer marker / legend swatch / battery fill |
| 999px | nav links, `.pill`, `.tag`, `.seg`, `.seg button`, `.ask-btn`, chips |
| 99px | `.meter`, `.stack` |
| 50% | pill dot (8 px), `.ic` (60 px), `.story-ic` (44 px), device dot (7 px) |

## Page Structure

Order in `<body>`: `header`, `main.wrap` (sections `#now`, `#plan`, then `div.cols` with `#savings` and `#system`), `footer`, then the chat button and panel (both `hidden` until the assistant is on). The four sections have class `reveal`.

**Header (lines 205 to 216).**
- `.logo` "my" + `<span>Energy</span>` (green).
- `.plant`: `<b id="plant-name">` ("Your plant" until `/api/site` loads, then `site.name`) and `<span id="plant-loc">` (`site.location`).
- `nav.nav` (`aria-label="Sections"`): links `#now` "Now", `#plan` "Plan", `#savings` "Savings", `#system` "System". The link of the section under the viewport's 45 to 50 % band gets `.active` (see Data Loading). Hidden at 860 px and below.
- `span#status.pill` (`role="status"`, `aria-live="polite"`): a dot `<i>` and `#status-text`. Starts as `pill` with "Connecting…".

### Status pill

`renderStatus()` (line 400) is the only place that sets it. The first matching rule wins:

| Order | Condition | Class | Text |
|------:|-----------|-------|------|
| 1 | last `/api/live` fetch failed (`!state.liveOk`) | `bad` | Can't reach the plant |
| 2 | `state.live` exists and `Date.now() - live.ts` is over 60 s | `warn` | Readings delayed |
| 3 | `state.plan` exists and `plan.available` is false | `warn` | No forecast: running on safe rules |
| 4 | no `state.live` yet | (none) | Connecting… |
| 5 | otherwise | `ok` | Running normally |

Dot: `--faint` by default; `ok` = `--ok` with the `beat` animation (2 s); `warn` = `--warn`; `bad` = `--bad`. In `warn` and `bad` the text takes that colour. A failed `/api/plan` fetch does not change the pill. `state.planOk` is set but never read. Called after every `loadLive`, after every `loadPlan`, and every 10 s.

### Section 1: Right now (`#now`, `h2#h-now`)

`p.meta#now-updated`: `Updated HH:MM` (24 h, `en-GB`, plant time, from `live.ts`). Empty until the first reading.

**Flow diagram.** `div#flow.flow` has `role="img"` and an `aria-label`. Initial label: "Energy flow, waiting for the first reading". After each reading: "Energy flow now: solar X kW, the factory uses Y kW, battery Z% and <battery sub-text>, grid <grid sub-text>."

SVG (`aria-hidden`): four grey tracks (`.track`, 3 px, `--border`, round caps) from each node anchor to the hub at (200,120): solar (72,48), grid (328,48), battery (72,192), load (328,192). On top, four animated lines (`.fl`, 3.5 px, round caps, `stroke-dasharray: 3 11`, `opacity: 0`, fade `.5s`). Each path is drawn from its node to the hub.

`setFlow(lineId, nodeId, power, intoCentre)` (line 416): the line gets `.on` (opacity 1, animation `flow 1.6s linear infinite`) when `|power| > 0.5` kW. `.rev` is set when `intoCentre` is false (animation direction reversed). Without `.rev` the dashes move node to hub. With `.rev` they move hub to node. Inline `animation-duration = max(0.45, 2.6 - |power|/60)` seconds (0 kW 2.6 s, 60 kW 1.6 s, 129 kW or more 0.45 s). The node gets `.on` with the same rule.

| Line | id | Stroke | Power (`/api/live`) | Moves to the hub when | Moves away from the hub when |
|------|----|--------|---------------------|-----------------------|------------------------------|
| Solar | `fl-solar` | `#FFB72B` | `solar_kw` | always | never |
| Grid | `fl-grid` | `#FF5A72` | net = `grid_import_kw - grid_export_kw` | net > 0 (buying) | net < 0 (selling) |
| Battery | `fl-batt` | `#15E6A0` | `battery_kw` | `battery_kw < 0` (discharging) | otherwise (charging) |
| Factory | `fl-load` | `#C7CDD6` | `consumption_kw` | never | always |

Hub: `circle.hub` r=10 at (200,120), fill `--card2`, stroke `--battery` 2 px. `circle.hub-ring` (same place, stroke `--battery` 1.5 px) runs `ring 2.4s ease-out infinite` (scale 1 to 2.6, opacity .6 to 0) at all times. `span.hub-label` "myEnergy" sits at `left:50%; top:47%`, hidden at 540 px and below.

Nodes: `div.node` is absolutely placed, `width: 150px`, `transform: translate(-50%,-30px)` so the icon circle is centred on the anchor. Inside: `.ic` (60 px circle, `--card2`, 1 px `--border`), `.nm`, `.v`, `.s`. `.on` glow: see "Colors outside the tokens". `#n-load` has no `.on` style (its ring is always `#3A404A`), and `.n-solar.on .ic svg` spins (`spin 18s linear infinite`).

| Node | id | Position (left, top) | Icon | Value element | Sub-text element |
|------|----|----------------------|------|---------------|------------------|
| Solar | `n-solar` | 18 %, 16 % | sun, `--sun` | `#t-solar` = `solar_kw` as `N kW` | `#t-solar-s`: `no weather data: clear-sky model` if `solar_source` is `clear-sky model`; else `of N kWp installed` (from `/api/site`, empty until it loads) |
| Grid | `n-grid` | 82 %, 16 % | bolt, `--grid` | `#t-grid`: `N kW in` (net > 0.5), `N kW out` (net < -0.5), else `Idle` | `#t-grid-s`: `buying` / `selling surplus` / `nothing bought or sold` |
| Battery | `n-batt` | 18 %, 64 % | CSS battery `#batt-ic`, `--battery` | `#t-batt` = `battery_soc` as `N%` | `#t-batt-s`: `charging N kW` (`battery_kw > 0.5`), `discharging N kW` (`< -0.5`), else `idle` |
| Factory | `n-load` | 82 %, 64 % | factory, `--text` | `#t-load` = `consumption_kw` as `N kW` | `#t-load-s`: `incl. <running device names>` or `base load` |

Battery icon: `span#batt-ic.batt-ic` (30 x 16 px, 2 px border, radius 4, nub 3 x 6 px). Its inner `<i>` has `width: var(--soc)`. `--soc` is set to `battery_soc` clamped to 0 to 100 %, width transition `.8s ease`.

**Side panel (`.side`).**
- `p.eyebrow` "What it's doing"; `p#now-reason.sentence` = `live.reason`, shown as text. Initial: "Waiting for the first reading…".
- `.price` box: "Grid price now" (`span.s`); `b#price-now` = `€0.27/kWh` (`live.tariff`, 2 decimals, the buy price: market price plus 0.10); `span#price-tag.tag`; `span#price-next.s`.
  - Tag, from `plan.hours[0]` (`renderPriceTag`, line 463): `cheap` gives "cheap hour" (`.tag.cheap`, blue); else `dear` gives "expensive hour" (`.tag.dear`, coral); else "average hour" (`.tag.std`, grey). `cheap` is checked first.
  - `#price-next`: `Cheapest in the next 24 hours: €0.24 at 06:00` (`summary.cheapest_price`, `summary.cheapest_at`).
  - With no plan or `available: false`, both texts are emptied. The tag keeps its last colour class.
- `.share`: "Solar share, last hour", a `.meter` with `i#share-bar` (width = share %, gradient `--sun` to `--battery`, transition `.8s ease`), and `b#share` = `round(live.solar_fraction * 100)%`. The backend value is a 60-minute window.
- Update: all of `renderNow()` runs with every `/api/live` reading (5 s). The price tag runs with every plan (60 s).

### Section 2: Tonight and tomorrow (`#plan`, `h2#h-plan`)

`p.meta#plan-updated`: `Plan updated HH:MM`, then `, weather from <forecast_source> at HH:MM` (if `forecast_fetched_at`), then ` (couldn't refresh since)` (if `forecast_error`). Empty when the plan is unavailable.

**Notice states** (`#plan-notice.card.notice`, `#plan-body` has the `hidden` attribute at first):
- Building (initial): "Building the plan…".
- Unavailable (`plan.available` false): the notice shows `plan.message` ("No weather forecast, so the system is running on its safe rules. The plan appears as soon as a forecast arrives."), class `card notice warn` (amber text, border `rgba(255,183,43,0.35)`). `#plan-body` is hidden. The page does not show `plan.forecast_error` here (checked in the browser).
- Cannot reach the server on the first fetch: "Can't reach the plant. Retrying in 10 seconds.". A plan already on screen stays.
- Available: notice hidden, `#plan-body` shown.

**Story** (`#story`, `aria-live="polite"`): class `story tone-<tone>`. `#story-ic.story-ic` (44 px circle, `aria-hidden`) gets an inline icon by tone; `#story-headline` and `#story-detail` get `story.headline` and `story.detail` as text.

| Tone | Icon (`ICONS.<tone>`) | Icon colour / circle background | Headlines (from `planner.summarize`) |
|------|-----------------------|---------------------------------|---------------------------------------|
| `sun` | sun | `--battery` / `rgba(21,230,160,0.12)` | Waiting for the sun; Running on the sun |
| `buy` | bolt | `--sun` / `rgba(255,183,43,0.12)` | Buying in the cheapest hours; Buying cheap power tonight |
| `hold` | pause (two bars) | no rule: `--muted` on `--card2` | Holding steady |

An unknown tone uses the `hold` icon.

**KPI tiles** (`.kpis`, three `.tile`):

| Tile | Label | Value | Sub-text |
|------|-------|-------|----------|
| 1 | Bought for the battery, next 24 h | `#k-buy` = `summary.buy_tonight_kwh` as `N kWh` | `#k-buy-s`: `at about €0.25, 13:00 to 15:00, 01:00 to 02:00` (`buy_price`, `buy_windows`); if nothing is bought: `N kWh without the sun` (`buy_without_sun_kwh` above 0) or `nothing needed` |
| 2 | Free solar into the battery | `#k-sun` = `summary.solar_to_battery_kwh` as `N kWh` | static: "next 24 hours" |
| 3 | Battery at its fullest | `#k-full` = `summary.fullest_battery_pct` as `N%` | `#k-full-s`: `at HH:MM` (`fullest_at`) |

**Legend** (`.legend`, `aria-hidden`): five swatches (10 x 10 px, radius 2): Solar forecast `--sun`; Consumption `--muted`; Grid bought for the battery `--grid`; Battery level `--battery`; Cheapest hours `rgba(55,138,221,0.45)`. The "now" line is not in the legend.

**Plan chart** (`.chart-box`: 280 px high, `fade .8s ease both`; `canvas#plan-chart`, `role="img"`).
- Library: Chart.js 4.4.0, `<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js">` in `<head>` (line 7). No `async`, no `defer`, no `integrity`.
- Type `line`, one category x axis, labels = `plan.hours[].label` (plant-local `HH:MM`, up to 36). Options: `responsive`, `maintainAspectRatio: false`, `animation: false`, `interaction: {mode:'index', intersect:false}`, legend off. The chart is created once. Later plans do `chart.data = ...; chart.update('none')`.
- Datasets (array order):

| # | Label | Data field | Line / fill | Axis | `order` | Other |
|--:|-------|------------|-------------|------|--------:|-------|
| 1 | Grid bought for the battery | `grid_buy_kw` | `#FF5A72` 1.5 px, fill `rgba(255,90,114,0.45)` | `y` (kW) | 3 | `stepped: 'after'` |
| 2 | Solar forecast | `solar_kw` | `#FFB72B` (width 3, default), fill `rgba(255,183,43,0.15)` | `y` | 2 | monotone curve |
| 3 | Consumption | `load_kw` | `#8C95A4` (width 3, default), dashed `[5,4]`, no fill | `y` | 1 | `stepped: 'after'` |
| 4 | Battery level | `battery_pct` | `#15E6A0` 2.5 px, no fill | `y2` (%) | 0 | monotone curve |

  All points are hidden (`pointRadius: 0`). A lower `order` draws on top, so the battery line is on top.
- Axes: `y` left, `min: 0`, `suggestedMax = max(20, highest solar, load or grid_buy value) * 1.1`, ticks `N kW`, grid `rgba(255,255,255,0.06)`. `y2` right, 0 to 100, ticks `N%`, no grid. `x`: no grid, `maxRotation: 0`, `autoSkip`, `maxTicksLimit: 10`, `offset: false`. All tick text `#8C95A4`.
- **Cheap hours** are drawn by the local plugin `cheapBands` (line 474): for each hour with `cheap: true`, a full-height rectangle `rgba(55,138,221,0.11)` from that hour's label to the next label. **Dear hours are not drawn on the chart.** `hours[].dear` is used only for the price tag.
- **"now" marker:** a dashed line (`[4,4]`, `#C7CDD6`) at the first label plus `minute/60` of one step, with the text "now" 5 px to the right and 12 px below the top. `minute` is the plant-local minute of `plan.generated_at`.
- Tooltip: Chart.js default look (`rgba(0,0,0,0.8)`), index mode (all four series), title = the hour label, rows `Label: N kW` or `Label: N%` (rounded; `%` for the battery axis).
- `battery_pct` is the level at the start of each hour (hour 0 is the live battery level).
- `aria-label` of the canvas: `Plan timeline for the next N hours. <headline>. <detail>`.
- Update: `/api/plan` every 60 s (30 s while unavailable, 10 s after a failed fetch).

### Section 3: Savings (`#savings`, `h2#h-save`)

`p.meta#s-month` = `<savings.month>, estimated` (for example "October 2026, estimated"; the month is the server's UTC month).

- **Segmented control:** `div.seg` (`role="tablist"`, `aria-label="Period"`), two `<button type="button" role="tab">`: `#sv-so` "This month so far" (`data-span="so_far"`, selected at start) and `#sv-full` "A full month" (`data-span="full_month"`). A click sets `state.span`, flips `aria-selected` on both and calls `renderSavings()` with the data already loaded (no new fetch). Selected look: `--card` background, `--text`, 1 px top highlight. Others: `--muted`.
- `L` = `savings[state.span]`. Numbers use `money()`: under 100 in absolute value `€12.34`, else grouped whole euros `€4,730` (`en-GB`).

| Element | Shows | Field(s) |
|---------|-------|----------|
| `p.big#s-total` | total saved | `L.saved_by_solar_eur + L.saved_by_battery_timer_eur + L.saved_by_myenergy_eur` |
| `#s-days` | `Day 18 of 31, out of a €7,601 bill without any of it` (so far) or `In a 30-day month, out of a ... bill without any of it` (full month) | `days_elapsed`, `days_in_month`, `L.bill_without_anything_eur` |
| `#s-co2` | `3,430 kg` | `L.co2_avoided_kg` (label "CO₂ avoided") |
| `#s-solar` | Solar panels | `L.saved_by_solar_eur` |
| `#s-batt` | Battery on a simple timer | `L.saved_by_battery_timer_eur` |
| `#s-saved` | myEnergy's planning (violet) | `L.saved_by_myenergy_eur` |
| `#s-bill` | Still paid | `L.bill_eur` |
| `#s-plan-s` | "What the software adds: it uses the forecast to decide when to buy and when to wait for the sun. N% of the bill." | `L.myenergy_pct_of_bill` |
| `p.foot#s-note` | "Estimated with a simulated month of weather, not measured. myEnergy is judged with an imperfect forecast (each day's cloud cover shifted at random), not with knowledge of the real weather." (changed 2026-10-18, commit `43fabfb`) | none (fixed text; `forecast_error_pct` is no longer shown) |

- **Stacked bar** (`div.stack`, `aria-hidden`: 14 px high, radius 99, gap 2 px): four `<i>` segments `#b-solar` (`--sun`), `#b-batt` (`--battery`), `#b-plan` (`--plan`), `#b-bill` (`#2A2F37`). Each width is `max(0, value) / bill_without_anything_eur * 100 %`. `#b-plan` is `max(4px, N%)` when the saving is above 0, else 0. Width transition `1s cubic-bezier(.2,.8,.2,1)`.
- **Layer rows** (`ul.layers`, four `li`, grid `12px 1fr auto`): marker (12 x 12 px, radius 3), title + explanation, amount. Order: Solar panels, Battery on a simple timer, myEnergy's planning, Still paid. The Solar and Battery rows have fixed explanation text. `li.mine` has `rgba(161,139,255,0.10)` background, `rgba(161,139,255,0.35)` border, and its amount is `--plan`. The other amounts are `--text`.
- Update: once at load, then every 5 minutes. If a fetch fails the last values stay and nothing is shown.

### Section 4: Your system (`#system`, `h2#h-sys`, no meta)

`dl.facts#facts` (grid `auto 1fr`, `gap: 10px 18px`). Initial: `Loading` / `…`. Filled by `renderSystem()` from `/api/site`:

| Term | Value |
|------|-------|
| Location | `location` |
| Solar | `N kWp` (`solar_kwp`) |
| Battery | `N kWh, up to N kW` (`battery_kwh`, `battery_power_kw`) |
| Reserve | `never below N%` (`reserve_pct`) |
| Tariff | `Changes every hour: the market price plus €0.10/kWh for grid fees and taxes` (`surcharge_eur_kwh`) |
| Export pays | `the market price minus €0.01/kWh` (`export_fee_eur_kwh`) |
| Prices from | `price_source` (the real source name, or "simulated prices (the market prices could not be fetched)") |
| Controlled devices | one `.dev` row per `site.devices` |

Device row: `<i class="dot">`, `Name, N kW`, and `span.st` from `live.devices` (matched by name): `Running, N kWh to go`, `Waiting, N kWh to go` (remaining above 0), or `Done`. With no live data the status is empty. `.dev.run` (device on): dot `--battery` with the `beat` animation. Otherwise the dot is `--faint` (7 px). `renderSystem()` also sets `#plant-name`, `#plant-loc` and the footer text. It runs once when the site loads and again on every `/api/live` reading (5 s).

### Footer

`footer > .wrap` (flex, `space-between`, wraps). Left: `span#footer`, "All times are the plant's local time." and, after `/api/site` loads, `All times are the plant's local time (Europe/Berlin).`. Right: "A demo with a simulated factory." and a link "Source code and the AI assistant on GitHub" to `https://github.com/karimtataa46/myenergy` (colour `--muted`, no `target`).

### Ask your plant (assistant)

- **Button** `#ask-open.ask-btn` (`hidden` at first; `aria-haspopup="dialog"`, `aria-controls="ask-panel"`): fixed, right 20 / bottom 20 px, 12 x 16 px padding, `--card`, border `rgba(21,230,160,0.4)` (`--battery` on hover), chat-bubble icon 18 px in `--battery`, text "Ask your plant".
- **Panel** `#ask-panel.ask-panel` (`role="dialog"`, `aria-labelledby="ask-title"`, `hidden`): fixed, right 20 / bottom 20 px, width 380 px, `max-height: min(560px, calc(100vh - 40px))`, flex column, `--card`, 1 px `--border`, radius 18 px. Parts:
  - Head: `h2#ask-title` "Ask your plant", `p.meta` "Answers from the live data, in German or English. It can't change settings.", close button `#ask-close` (`×`, `aria-label="Close"`).
  - Log `#ask-log` (`aria-live="polite"`, scrolls, `min-height: 140px`): starts with one bot message "Ask me what the plant is doing, what it plans for tonight, or what it saves."
  - Chips `#ask-chips`: "Wie voll ist die Batterie gerade?", "Kauft die Anlage heute Nacht Strom?", "How much did we save this month?". A click sends the chip text as the question.
  - Form `#ask-form`: `label.sr-only` "Your question", `input#ask-input` (`maxlength="500"`, `autocomplete="off"`, placeholder "Frag etwas… / Ask something…"), `button#ask-send` "Send" (green, `#04110B` text, 50 % opacity when disabled). The input has `outline: none` and its border turns `--battery` on focus.
- **Message styles** (`<p class="msg ...">`, max-width 88 %, padding 9 x 12 px, radius 12, `white-space: pre-wrap`, `overflow-wrap: anywhere`): `.me` right-aligned, `rgba(21,230,160,0.14)`; `.bot` left-aligned, `--card2`; `.pending` text `--muted` (shown as "Reading the plant data…" on `bot pending`); `.err` text `--warn`.
- **When it shows:** the server must report the assistant: `GET /api/assistant` returns `available: true`. The check runs at load and every 60 s. If it is false, or the fetch fails, the button is hidden. If true and the panel is closed, the button is shown. With no `AGENT_URL` (the public demo) the button never appears.
- **Open:** panel shown, button hidden, focus into the input. **Close:** `×` or the `Escape` key; the panel hides, the button shows, focus goes to the button.
- **Sending** (`sendQuestion`): trims the text, ignores empty text or a send in progress, disables Send, hides the chips for good (until reload), clears the input, adds the `me` message and the pending bot message, posts, then replaces the pending text, removes `pending`, adds `err` on failure, scrolls to the bottom, re-enables Send and refocuses the input.
- **Request:** `POST /api/ask` with JSON `{question, session_id}`. `session_id` is `crypto.randomUUID()` (fallback `Date.now().toString(16) + '-' + random hex`), kept in `sessionStorage` under `ask-session`, so one conversation per browser tab. Storage access is in `try/catch`. The server accepts 1 to 500 characters; the input stops at 500.
- **Errors shown** (class `err`): the server's `error` text, else "The assistant can't answer right now."; on a network failure "Can't reach the plant. Check the connection and try again." Server texts: "Please type a question." (422), "The assistant isn't set up on this server." (503), "That's a lot of questions at once. Please wait a minute." (429), "The assistant took too long to answer. Please try again." (504), "The assistant can't answer right now. Please try again later." (503), "The assistant had no answer. Try asking in a different way." (503). There is no client timeout on the fetch.
- **Answers are model output and are always set with `textContent`, never as HTML** (comment at line 638). `tests/test_e2e.py` checks that an `<img onerror>` in an answer stays text.

## Data Loading and Rendering

**Fetching.** `getJSON(url)` calls `fetch(url, {cache: 'no-store'})` and throws on a non-OK status. `fetchOrNull(url)` wraps it in `try/catch` and returns `null` on any failure (network, HTTP or bad JSON). Only the network call is caught on purpose (comment at line 696): an error while rendering is a bug and must surface. `/api/ask` uses its own `fetch` (no `cache` option).

**Start.** At the end of `<body>` the script calls `loadSite(); loadLive(); loadPlan(); loadSavings(); loadAssistant();` at once, then sets the timers.

| What | Call | Timing | On failure |
|------|------|--------|------------|
| Site facts | `loadSite` `/api/site` | once; render also runs on each live reading | retries every 10 s (`setTimeout`) until it works; no refresh after success |
| Live reading | `loadLive` `/api/live` | `setInterval` 5000 ms | `liveOk = false`, pill "Can't reach the plant", tiles keep the last values, next try in 5 s |
| Plan | `loadPlan` `/api/plan` | `setTimeout` chain: 60000 ms (available), 30000 ms (unavailable) | 10000 ms; first time the notice says "Can't reach the plant. Retrying in 10 seconds."; a plan already shown stays |
| Savings | `loadSavings` `/api/savings` | `setInterval` 300000 ms | keeps the last values |
| Assistant | `loadAssistant` `/api/assistant` | `setInterval` 60000 ms | button hidden |
| Pill | `renderStatus` | `setInterval` 10000 ms, plus after each live and plan load | n/a |

**State** (`state`): `site`, `live`, `plan`, `savings`, `span` (`'so_far'`), `liveOk`, `planOk`. `chart` and `planTimer` are separate globals. The functions `loadLive` and `loadPlan` are global; the E2E test calls them.

**Placeholders before data:** `…` in every value (`#t-solar`, `#t-grid`, `#t-batt`, `#t-load`, `#price-now`, `#share`, `#k-buy`, `#k-sun`, `#k-full`, `#s-total`, `#s-co2`, `#s-solar`, `#s-batt`, `#s-saved`, `#s-bill`); "Waiting for the first reading…" (sentence); "Connecting…" (pill); "Building the plan…" (plan notice); "Your plant" (header name); `Loading` / `…` (facts). `renderNow()` returns early while `live` is empty or has no `ts`.

**Number animation.** `tween(el, to, fmt, exact)` (line 384) glides a number from its previous value (0 the first time) in 700 ms with ease-out cubic (`1 - (1 - k)^3`) using `requestAnimationFrame`. The last frame shows `exact` (or `fmt(to)`), so the final text is never a rounding of an animation step. It is skipped (text set at once) when the value did not change or when `prefers-reduced-motion: reduce` was on at page load (`calm`, read once). A newer value cancels an older animation. Tweened: `#t-solar`, `#t-load`, `#t-batt`, `#share`, `#k-buy`, `#k-sun`, `#k-full`, `#s-total`, `#s-co2`, `#s-solar`, `#s-batt`, `#s-saved`, `#s-bill`. Not tweened: `#t-grid`, `#price-now`, all sub-texts.

**Formats.**
- Power: `Math.round` + ` kW` (`kw()`). Energy: `N kWh` (the plan KPI values use the API's already rounded integers). Battery and shares: `Math.round` + `%`. CO₂: grouped integer + ` kg`. Installed solar: `N kWp`.
- Price: `eur()` = `€` + `toFixed(2)`; per kWh adds `/kWh`. Money: `money()` (see Savings).
- Clock: `clock(iso)` = `Intl.DateTimeFormat('en-GB', {hour:'2-digit', minute:'2-digit', timeZone})`, 24 h `HH:MM`. `timeZone` is `site.timezone` (Europe/Berlin). Chart labels, buy windows, `fullest_at` and `cheapest_at` arrive from the API already as plant-local `HH:MM`.
- Unit and number characters in the text: `€`, `…`, `₂` (CO₂), `×`.

**Reveal and menu.**
- `.reveal` sections start at `opacity: 0; translateY(14px)` and get `.in` (opacity 1, no transform; `.6s ease`) from an `IntersectionObserver` (`threshold: 0.08`) the first time they are visible. Without `IntersectionObserver`, `.in` is added at once.
- A second observer (`rootMargin: '-45% 0px -50% 0px'`, watching `main section[id]`) sets `.active` on the nav link whose `hash` matches the section crossing that thin band.

## Responsive Behavior

Two media queries for layout, plus the reduced-motion query. The viewport meta is `width=device-width, initial-scale=1.0`.

| Width | What changes |
|-------|--------------|
| 860px and below | `.hero` and `.cols` become one column (gaps stay 26 / 24 px). `.nav` is hidden. |
| 540px and below | `.node` width 118 px and `translate(-50%,-25px)`; `.node .v` 17 px; `.ic` 50 x 50 px (the SVG inside stays 26 px); `.node .s` and `.hub-label` hidden; `.big` 28 px; `.side .sentence` 18 px. Chat button at right/bottom 16 px. Chat panel becomes a bottom sheet: `left:0; right:0; bottom:0; width:auto; max-height:85vh; radius 16px 16px 0 0`. Chat input font 16 px (comment: stops iPhones zooming into the field). |
| no query | `.kpis` (auto-fit, 180 px minimum: 3, 2 or 1 columns), the header bar (wraps; on a phone the status pill drops to its own line), `.sec-head`, `.legend`, `.sv-top`, `.facts` and the footer wrap. |

Measured: no horizontal scroll at 390 px; at 700 px the KPIs are three columns; at 390 px they are one column and the cards are 350 px wide.

## Motion

| Animation | Where | Timing |
|-----------|-------|--------|
| `flow` (dash offset to -28) | `.fl.on` flow lines | 1.6 s linear infinite; inline duration `max(0.45, 2.6 - kW/60)` s; `.rev` reverses direction |
| `ring` (scale 1 to 2.6, opacity .6 to 0) | `.hub-ring` | 2.4 s ease-out infinite, always |
| `spin` | solar icon SVG while `.n-solar.on` | 18 s linear infinite |
| `beat` (box-shadow pulse 0 to 6 px) | ok dot of the pill; `.dev.run .dot` | 2 s ease-in-out infinite |
| `fade` (opacity 0 to 1) | `.chart-box` | .8 s ease, runs when the plan body is first shown |
| Reveal | `.reveal` to `.in` | opacity and transform .6 s ease |
| Number glide | `tween()` (JavaScript) | 700 ms, ease-out cubic |
| Transitions | `.fl` opacity .5 s; `.ic` box-shadow and border-color .5 s; `.batt-ic i` width .8 s ease; `.share .meter i` width .8 s ease; `.stack i` width 1 s `cubic-bezier(.2,.8,.2,1)`; `.nav a` and `.seg button` colour and background .2 s | |
| Smooth scroll | `html` `scroll-behavior: smooth` | |
| Chart.js | `animation: false`; `update('none')` | the chart box fades in instead |

**Reduced motion** (`@media (prefers-reduced-motion: reduce)`, line 198): `*, *::before, *::after {animation:none !important; transition:none !important; scroll-behavior:auto !important}` and `.reveal {opacity:1; transform:none}`. In JavaScript, `calm` makes `tween()` set values at once. Measured with reduced motion on: hub ring, pill dot and flow lines have `animation-name: none`; the flow lines still show (static dashes) when `.on`.

## Accessibility

What exists:
- `<html lang="en">`. Every `<section>` has `aria-labelledby` pointing at its `h2`.
- `nav` has `aria-label="Sections"`.
- Status pill: `role="status"`, `aria-live="polite"`. It always has text, so colour is not the only signal. The price tag also has text.
- Flow diagram: `div#flow` has `role="img"` and an `aria-label` rewritten on every reading (every 5 s). The SVG and node icons are `aria-hidden="true"`.
- Story: `#story` has `aria-live="polite"`; its icon is `aria-hidden`. The text is rewritten at each plan fetch.
- Chart canvas: `role="img"` with an `aria-label` (headline and detail). Legend and stacked bar are `aria-hidden`.
- Savings switch: `role="tablist"` (`aria-label="Period"`) with `role="tab"` and `aria-selected`. The tabs are real `<button>` elements.
- Chat: button with `aria-haspopup="dialog"` and `aria-controls`; panel `role="dialog"` with `aria-labelledby`; log `aria-live="polite"`; close button `aria-label="Close"`; the input has a `label.sr-only` (`position:absolute; 1px; overflow:hidden; clip:rect(0 0 0 0)`). `Escape` closes the panel and focus returns to the button. Opening moves focus to the input.

Not present (facts, from reading the code):
- Tabs have no `aria-controls`, no `role="tabpanel"` and no arrow-key handling.
- The chat dialog has no `aria-modal`, no focus trap and no backdrop. The button has no `aria-expanded`.
- No skip link. No custom `:focus-visible` styles: links and buttons use the browser default focus ring. Only the chat input replaces its outline (with a green border).
- Text in German (chips, placeholder, possible answers) sits in a page with `lang="en"` and has no `lang` attribute.
- `--faint` text (3.1 to 3.5:1) is used for sub-texts, footnotes and the footer.
- The values inside `#flow` (node names and numbers) are children of `role="img"`, so they are exposed through its `aria-label` only.

## Icons

All icons are inline SVG written in the HTML or in the script. No icon font, no image files, no emoji.
- Common attributes: `viewBox="0 0 24 24"`, `fill="none"`, `stroke="currentColor"`, `stroke-width="2"`; round caps or joins. Colour comes from `color` on the container. All are outlines (stroke), none is filled.
- **Sun:** circle r 4 plus eight rays (`stroke-linecap: round`). Solar node (26 px) and `ICONS.sun` (story, 22 px).
- **Bolt:** `M13 2 4 14h7l-1 8 9-12h-7z` (`stroke-linejoin: round`). Grid node and `ICONS.buy`.
- **Pause:** `M9 5v14M15 5v14` (`stroke-linecap: round`). `ICONS.hold` (also the fallback icon).
- **Factory:** `M3 21V9l6 4V9l6 4V5h6v16z` plus three window marks. Factory node.
- **Chat bubble:** `M21 12a8 8 0 0 1-11.6 7.1L4 20.5l1.4-4.9A8 8 0 1 1 21 12z`. Chat button (18 px, `--battery`).
- **Battery** is not SVG: `span.batt-ic` drawn with CSS (see Right now).
- **Close** is the text character `×` (22 px). The dots, legend swatches and layer markers are CSS shapes (`<i>`).
- The flow diagram is its own SVG (`viewBox="0 0 400 300"`): tracks, dashed lines, hub, ring.
- `ICONS` (line 364) holds the three story icons as strings and is inserted with `innerHTML` (static strings only).

## Conventions For Changes

- Style with the `:root` variables. Keep the colour meanings: amber sun, green battery, coral grid, blue cheap hours, violet myEnergy's planning. Do not give a colour a second meaning.
- If you change a token value, also change its hex copies: the four `stroke` attributes on the flow lines, the chart colours in `drawChart` and `cheapBands`, the `#2A2F37` bill segment, and the tints in the table above. `tests/test_e2e.py` counts chart pixels near `#15E6A0`, so the battery line must stay that colour (within 40 per channel).
- Keep one HTML file with its own `<style>` and `<script>`. No framework and no build step, unless the owner decides otherwise. Chart.js from the CDN is the only external resource.
- Keep the section order and the pattern: `<section id="..." aria-labelledby="h-..." class="reveal">` with `.sec-head` (`h2` + `.meta`) and a `.card`. A new section also needs a nav link and a heading id.
- Use `font-variant-numeric: tabular-nums` for every number that changes. Use `tween()` for live numbers and pass `exact` when the final text must equal the API value.
- Keep times plant-local: use the API's `label` strings or `clock(iso)` (which uses `site.timezone`). Do not call `toLocaleTimeString` without a time zone.
- Fill text with `textContent`. Never put model output (or any user text) into `innerHTML`. The existing `innerHTML` uses are static icon strings and the facts list (built from `/api/site`, which holds server constants).
- Catch only the network call (`fetchOrNull`). Do not wrap rendering code in `try/catch` to hide errors.
- Keep `calm`/`prefers-reduced-motion` working: CSS animations are covered by the global rule. New JavaScript motion must check `calm`.
- Use the two existing breakpoints (860 px and 540 px). Keep chat input at 16 px on phones.
- Keep these ids, class names and texts: `tests/test_e2e.py` uses `#story-headline`, `#story-detail`, `#k-buy`, `#k-full`, `#plan-chart`, `#status-text`, `#t-solar`, `#t-load`, `#t-batt`, `#t-grid`, `#now-reason`, `#plant-name`, `#facts`, `#s-saved`, `#plan-notice`, `#plan-body`, `#ask-open`, `#ask-panel`, `#ask-input`, `#ask-send`, `.msg.me`, `.msg.bot`, `.msg.bot.err`, the global functions `loadLive` and `loadPlan`, the texts "Running normally", "Waiting for the first reading…", "No forecast: running on safe rules", "Can't reach the plant", the placeholder `…`, the chip "Wie voll ist die Batterie gerade?" and the error text "can't answer right now". `#k-buy` must read exactly `<buy_tonight_kwh> kWh` and `#k-full` exactly `<fullest_battery_pct>%`.
- The page is served with no-cache headers (below), so an edit shows on the next reload. Do not add a service worker or cache-busting build step.

## Known UI Facts

- `GET /` returns `frontend/index.html` with `Cache-Control: no-cache, no-store, must-revalidate`, `Pragma: no-cache`, `Expires: 0` (`_NOCACHE` in `main.py`). `/static` serves the whole `frontend/` folder, so `/static/index.html` is the same file without those headers (only `ETag` and `Last-Modified`, checked with curl). `index.html` is the only file in `frontend/`.
- The old pages `/estimate`, `/facility`, `/sim`, `/plan` were removed and return 404 (see `architecture-context.md`). `/plan` the path is 404; `#plan` is only the section anchor.
- There is no `<link rel="icon">`, no `<noscript>` and no meta description. `/favicon.ico` returns 404. Without JavaScript the page shows only its placeholders.
- **Chart.js needs internet in the browser.** It is a parser-blocking `<script>` in `<head>`. If the CDN is blocked, `Chart` is undefined: `drawChart` throws inside `renderPlan`, which stops `loadPlan` before it sets its timer. Result (measured): the story and KPIs show once, the chart stays empty, the plan is never refreshed again (`planTimer` stays `null`), and the pill still says "Running normally". The E2E browser is a separate process and loads Chart.js from the CDN. The Python `no_internet` fixture does not block it.
- If `/api/live` returns `{}` (before the first tick), `state.live` is `{}`. The pill then says "Running normally" while the sentence says "Waiting for the first reading…" (measured with a stubbed response).
- "Readings delayed" compares the browser clock with the server's `ts`. A wrong browser clock changes it.
- `timeZone` for `clock()` is the browser's own zone until `/api/site` has loaded. The savings month name (`October 2026`) and "Day N of M" use the server's UTC date, not plant time.
- The numbers on the page have different freshness. `/api/live` changes every 5 s. The plan is recomputed on every request (the page asks every 60 s). `/api/savings` is simulated and changes only when the server's UTC day changes.
- `N% of the bill` in the violet row is `myenergy_pct_of_bill` = the saving divided by the cost with panels and the timer (before the software), not by the final "Still paid" figure (`savings.py`).
- Tone colours do not follow the source colours: tone `sun` is green, tone `buy` is amber. Tone `hold` has no colour rule.
- Hours flagged `dear` are never drawn on the chart. The legend swatch for cheap hours is darker (0.45) than the band (0.11).
- When the plan is unavailable the notice shows `plan.message` only. `plan.forecast_error` is shown only as "(couldn't refresh since)" when a plan exists.
- `/api/live` fields not used by the page: `zones`, `action`, `co2_saved_kg`, `cost_saved_eur`, `upcoming_solar_kw`, `solar_peak_kw`, `devices[].urgency`. `/api/plan` fields not used: `site`, `summary.buy_until`, `dearest_at`, `dearest_price`, `hours[].time`, `hours[].price`. `/api/site` `tariff` and `/api/savings` `weather` are not used.
- With the real forecast the chart shows up to 36 hourly points. It can have fewer late in the UTC day (see `architecture-context.md`, Known Limitations 11).
- README "What it does" matches the page in structure and order. Differences in wording: README says the plan section shows "the grid energy bought tonight" (the tile says "Bought for the battery, next 24 h"), and README names two pill problems while the page has four texts (adds "Readings delayed" and "Connecting…"). `docs/DESIGN.md` is outdated (four pages) and does not describe this page.
