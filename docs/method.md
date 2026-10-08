# How the Dhuaan smoke model works

Dhuaan is a fire-only smoke model. It answers three questions for every place in the domain: when does farm-fire smoke arrive, how much is there, and which fires sent it. It does not model traffic, industry, dust or chemistry, so its output is a "smoke index" in µg/m³-equivalent units, converted to an estimated PM2.5 increment with one calibrated factor.

The code is in `backend/dhuaan/model/` (small numpy modules, 32 tests in `backend/tests/model/`). Parameter values below are the defaults in `backend/dhuaan/model/params.py`.

## Domain and grids

| Item | Value |
|---|---|
| Domain | lon 72.5 to 79.0 E, lat 28.0 to 32.75 N (Punjab on both sides of the border, Haryana, Delhi/NCR, west UP, north Rajasthan) |
| Met grid | 0.25°, 27 × 20 = 540 points (Open-Meteo) |
| Output grid | 0.1°, 66 × 48 cells |
| Internal node grid | 0.025° (about 2.5 km), for deposition and convolution |
| Time axis | t0 − 24 h to t0 + 72 h, hourly, 97 frames |
| Receptors | 2,316 places: 867 villages, 469 towns and 79 cities (GeoNames), 611 schools (OSM), 290 pre-2022 Delhi ward centroids |

## Step 1: fires to sources

**Static hotspot mask.** Refineries, a power plant, landfills and kilns show up as "fires" all year. Before modelling, Dhuaan drops any FIRMS detection within 1 km of a static hotspot. A hotspot is a 0.01° cell (about 1 km) where VIIRS saw a detection on at least 8 distinct days between 1 Jan and 31 Aug 2025, outside the burning season. That rule was fixed before looking at the result. It gives 96 cells (`backend/data/static_hotspots.json`), which masked 1,357 detections in the Oct to Nov 2025 backtest window.

**Clustering.** Two detections are neighbours when they are within ε = 1.5 km and 6 h of each other. Clusters are the connected components of that graph (single linkage, DBSCAN with min_samples = 1). Each cluster gets the district and state of its centroid from geoBoundaries ADM2 polygons, including Pakistani Punjab west of the border.

**Emission.** Each detection is treated as two hours of burning at its fire radiative power:

$$M_k = \sum_{i \in k} \mathrm{FRP}_i \cdot 7200\,\mathrm{s} \cdot c_e, \qquad c_e = 0.02\ \mathrm{kg\ PM_{2.5}\ per\ MJ}$$

A detection without FRP (geostationary GK2A, for example) gets the median FRP of the run's other detections, or 10 MW if none has FRP. The mass is released as 20 to 400 particles per cluster (at most 50,000 per member), spread evenly over the burn window [first detection − 0.5 h, last detection + 1.5 h], with 300 m position jitter. Only fires detected in the 48 h before t0 are modelled.

**Afternoon fires.** The polar-orbiting satellites behind FIRMS pass over Punjab around 13:30 IST, and most burning now happens later (see the afternoon ratio below). The model has three modes:

- `observed`: add LSA SAF Meteosat-IODC FRP-PIXEL detections (15-minute geostationary data) as ordinary sources. This is the live default. If LSA SAF is unavailable, the pipeline falls back to `estimated`.
- `estimated`: for each cluster whose last polar detection was before 16:00 IST, add an extra mass $M^{aft}_k = r_d \cdot \sum \mathrm{FRP}^{polar} \cdot 7200 \cdot c_e$, released between 16:00 and 19:00 IST. Here $r_d$ is the district's afternoon ratio.
- `none`: polar detections only.

## Step 2: transport

**Mixed-layer wind.** At each met point the advecting wind is the mean of the levels inside the boundary layer: 10 m always, 925 hPa (about 750 m) when BLH ≥ 750 m, 850 hPa (about 1500 m) when BLH ≥ 1500 m. Winds and BLH are interpolated bilinearly in space and linearly in time.

**Advection and turbulence.** Particles move with a midpoint (RK2) step of Δt = 900 s plus a random walk:

$$\mathbf{x}_{n+1} = \mathbf{x}_n + \Delta t\,\mathbf{u}\!\left(\mathbf{x}_n + \tfrac{\Delta t}{2}\mathbf{u}(\mathbf{x}_n, t_n),\ t_n + \tfrac{\Delta t}{2}\right) + \sqrt{2K_h\Delta t}\ \boldsymbol{\xi}, \qquad \boldsymbol{\xi} \sim \mathcal{N}(0, I)$$

The horizontal diffusivity rises with mixing depth, from $K_h$ = 1,000 m²/s at BLH ≤ 300 m to 5,000 m²/s at BLH ≥ 1,500 m, linear in between.

**Removal.** Particle mass decays as $w = w_0 \exp(-\mathrm{age}/\tau)$ with τ = 48 h, a single lumped term for deposition and dilution out of the domain.

## Step 3: concentration and the ensemble

**Concentration.** Particles are deposited cloud-in-cell onto the 0.025° node grid, convolved with a 2D Gaussian kernel of width h = 10 km, and divided by the local boundary-layer height:

$$C(\mathbf{x}, t) = 10^{3}\ \frac{\sum_p w_p\, G_h(|\mathbf{x} - \mathbf{x}_p|)}{\max(\mathrm{BLH}(\mathbf{x}, t),\ 50\,\mathrm{m})}, \qquad G_h(r) = \frac{1}{2\pi h^2} e^{-r^2/2h^2}$$

With $w$ in kg, $G_h$ in km⁻² and BLH in m, $C$ comes out in µg/m³. Dividing by BLH is what makes nights bad: the same smoke mass under a 200 m night-time layer gives several times the concentration it gives under a 1.5 km afternoon layer. The map's "mixing height" band shows the forecast domain-mean BLH so viewers can see this.

**Ensemble.** Five members perturb the met, all sharing the same random numbers, so the spread comes only from the perturbations:

| Member | Wind speed × | Wind direction | K_h × |
|---|---|---|---|
| 0 | 1.00 | 0° | 1.0 |
| 1 | 0.85 | +15° | 0.5 |
| 2 | 1.15 | −15° | 2.0 |
| 3 | 0.85 | −15° | 2.0 |
| 4 | 1.15 | +15° | 0.5 |

Each place's forecast `series` is the member median; `p10` and `p90` give the band.

**Calibration to PM2.5.** $\widehat{\mathrm{PM}}_{2.5}^{smoke} = \alpha\, C$. α is fitted by least squares through the origin on the backtest fit period (below). The live runs use $\alpha_B$ = 0.1643 (`backend/out/latest/meta.json`, `calibrated: true`) as the pooled value. An exploratory, not pre-registered, regional fit on the same fit period gives $\alpha_B$ = 6.80 for the 3 Delhi stations and 0.149 for the 6 Punjab stations (`exploratory_regional` in `backtest.json`). The live pipeline uses those as a provisional calibration in Delhi/NCR and Punjab/Haryana and the pooled value elsewhere. Pearson r is computed on raw model smoke, so no choice of α changes it.

**Arrival.** Arrival is the first hour at or after t0 when the median series reaches 0.15 × scale, where scale is the 99th-percentile smoke over the run. In the 8 Oct 12:00 UTC run the threshold was 25.5 smoke units. Arrival windows come from the earliest and latest member.

## Step 4: attribution and exposure

**Attribution.** Every particle keeps its cluster label, so the concentration splits exactly by cluster and shares at a place sum to 1 by construction. Per-cluster fields are accumulated over t0 to t0 + 48 h; districts and states are sums over their clusters. Each place lists its top 5 districts plus "Other".

**Exposure ranking.** Each cluster's harm score is the people-hours of smoke it causes downwind over the next 48 h:

$$E_k = \sum_{t=t_0}^{t_0+48\,\mathrm{h}} \sum_{\mathrm{cells}\ c} P^{eff}_c(t)\, C_k(c, t)$$

$P^{eff}$ is HRSL population per 0.1° cell, multiplied by 1.5 between 07:00 and 14:00 IST in cells that contain a school. $E_k$ is computed with the adjoint (convolve population / BLH once per hour and sample it at the particles), which equals the forward sum at the cost of one convolution per hour. The district page sorts clusters by $E_k$ and states how few clusters cause most of the exposure.

## The afternoon ratio and the 93% fact

`backend/data/facts.json` holds the headline: of 33,074 GK2A detections over Punjab between 12:00 and 18:59 IST in Oct to Nov 2025, 93.0% fall at or after 16:00 IST, after the last polar pass. With confidence flags 2 to 3 only, the share is 96.2% of 19,392. The source is the GK2A-AMI hourly fire detections for Punjab and Haryana (Jethva 2026, NASA GSFC / Morgan State Univ., Zenodo doi:10.5281/zenodo.20084790, CC BY 4.0).

The per-district ratio for `estimated` mode (`backend/data/afternoon_ratio.json`) is a shrunk count ratio:

$$r_d = \frac{G_d + m R}{V_d + m}, \qquad m = 30, \qquad r_d \in [0.25,\ 4.0]$$

$G_d$ is GK2A detections (flag ≥ 2) at or after 16:00 IST, $V_d$ is FIRMS VIIRS + MODIS detections with static hotspots masked, and $R$ is the pooled ratio. It compares counts of 4 km and 375 m / 1 km pixels, so it is a rough scale factor, not an energy ratio. Ratios exist only for Punjab and Haryana districts (the dataset's coverage); other districts use the pooled default, 1.117. Examples: Barnala 4.0 (capped), Sangrur 1.14, Amritsar 0.25.

## Backtest protocol (pre-registered)

The protocol and metric definitions were written down before the run (`backend/dhuaan/backtest/metrics.py`).

- Window: 25 Oct to 20 Nov 2025, around the 11 Nov 2025 episode. One forecast per day issued at 00:00 UTC (05:30 IST), using only fires detected in the 48 h before issue. Scored lead: 12 to 35 h. 3 ensemble members, median.
- Split: α fitted on 25 Oct to 5 Nov; every metric is on 6 to 20 Nov (held out). No parameter was tuned on the held-out period.
- Configurations: **A** = FIRMS VIIRS/MODIS only. **B** = A plus GK2A afternoon detections (flags 2 to 3, Punjab and Haryana only, each given the median VIIRS/MODIS FRP because GK2A has no FRP). GK2A is a research dataset published after the season, so B shows what the forecast would have been with hourly afternoon fires.
- Stations: OpenAQ reference monitors with at least 80% hourly PM2.5 in the window. Nine passed (6 PPCB in Punjab, 3 DPCC in Delhi); Hardev Nagar, Bathinda was excluded at 79.2%.
- Observed signal: PM2.5 excess = PM2.5 minus the trailing 7-day 10th percentile at the same station.
- Episode: at least 3 consecutive hours with excess ≥ 60 µg/m³. Hit: the forecast reaches 60 at any hour within 6 h of the episode. False alarm: a forecast episode that overlaps no observed episode (±6 h). Lead time: per hit, episode start minus the earliest issue time (at least 12 h before) whose forecast crosses 60 in the window.
- Met: Open-Meteo Historical Forecast API (archived operational forecasts at 0.25°, not reanalysis). The archive stitches the first hours of successive runs, so winds beyond about a day of lead are better than a forecaster had at issue time. Treat the skill as an upper bound.

Results are in `backend/out/latest/backtest.json` and on the `/backtest` page. The README has the table.

## Limitations

- Fire smoke only. In Delhi the observed excess also contains local and regional non-fire pollution, which this model cannot represent. Fit-period means show it: in Delhi the observed excess averaged 135 µg/m³ against raw model smoke of 21.7 (A) and 27.7 (B).
- One pooled α (the pre-registered calibration). Punjab stations, where the model is noisy close to the fires, pull α down to about 0.16 to 0.19, while Delhi alone would want about 7 to 9. With the pooled α, calibrated forecasts rarely reach 60 µg/m³, so the episode hit rate is near zero. The exploratory regional α lifts Delhi to 57 of 57 episodes hit, but only because the observed excess and the forecast both sit at or above 60 µg/m³ in about 78% of held-out hours there; R² stays strongly negative.
- No plume rise, no vertical structure beyond the mixed-layer mean, no chemistry or secondary aerosol, one lumped removal time.
- The emission factor and burn duration are literature-style constants, not fitted.
- The afternoon ratio is a pixel-count ratio between sensors with very different footprints.
- LSA SAF Meteosat-IODC reported no detections in the domain in the 8 Oct 2026 12:00 UTC run (23 of 23 hourly slots read), so live evening detection is still unproven this season.
- Population is HRSL 2016-era imagery; school locations come from OSM and are incomplete.
- Delhi wards are the pre-2022 (290-ward) boundaries.
