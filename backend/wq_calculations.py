"""
wq_calculations.py — HydroCore Water Quality Pure Calculation Engine
=====================================================================
All functions are stateless (no DB access).  Pass prepared data in,
receive results out.  Suitable for unit testing without a database.

Standards implemented:
  - CCME Water Quality Index (CCME 2001)
  - SANS 241:2015 risk classification
  - Blue Drop scoring (DWS, 4-category weighted)
  - Ion Balance Error (Stumm & Morgan, charge balance in meq/L)
  - Mann-Kendall trend test + Sen's slope (Gilbert, 1987)
  - Langelier Saturation Index + Ryznar Stability Index
  - Carlson Trophic State Index (Carlson, 1977)
  - Piper diagram barycentric coordinates
  - Stiff diagram polygon construction
"""

import math
from datetime import date as date_cls

# ─── Ion balance equivalent weights (g/eq) ────────────────────────────────────
ION_EQ_WEIGHTS = {
    # cations
    'CA':   20.04,
    'MG':   12.15,
    'NA':   22.99,
    'K':    39.10,
    'NH4':  18.04,
    # anions
    'HCO3': 61.01,
    'CO3':  30.00,
    'CL':   35.45,
    'SO4':  48.03,
    'NO3':  62.00,
    'NO2':  23.00,
    'FL':   19.00,
}

ION_TYPES = {
    'CA': 'cation', 'MG': 'cation', 'NA': 'cation', 'K': 'cation', 'NH4': 'cation',
    'HCO3': 'anion', 'CO3': 'anion', 'CL': 'anion', 'SO4': 'anion',
    'NO3': 'anion', 'NO2': 'anion', 'FL': 'anion',
}

# Blue Drop category weights (DWS Blue Drop Programme)
BLUE_DROP_WEIGHTS = {
    'microbiological':     0.50,
    'chemical_health':     0.30,
    'chemical_aesthetic':  0.10,
    'physical':            0.10,
}


def ion_to_meq(code: str, mg_L) -> float:
    """Shared ion mg/L -> meq/L conversion using ION_EQ_WEIGHTS. Returns 0.0
    for unknown codes or None input. Single source of truth — used by
    compute_piper_data, compute_stiff_data, compute_sar."""
    eq = ION_EQ_WEIGHTS.get(code)
    if eq is None or mg_L is None:
        return 0.0
    return max(0.0, float(mg_L)) / eq


# ─── CCME Water Quality Index ─────────────────────────────────────────────────

def compute_ccme_wqi(measurements: list, approved_only: bool = True) -> dict:
    """
    Compute CCME-WQI for a set of measurements across a time period.

    measurements: list of dicts, each with keys:
        indicator_code  str
        measured_val    float | None
        upper_std       float | None
        lower_std       float | None
        quality_flag    str   (only 'Approved' used when approved_only=True)
        is_censored     bool  (censored values are excluded from F2/F3 calc)

    Returns dict: {wqi_score, category, F1, F2, F3, n_variables,
                   n_failed_variables, n_total_tests, n_failed_tests,
                   excursion_sum, approved_only}
    """
    if approved_only:
        measurements = [m for m in measurements if m.get('quality_flag') == 'Approved']

    # Filter to measurements that have a standard and a real value
    testable = [
        m for m in measurements
        if m.get('measured_val') is not None
        and not m.get('is_censored', False)
        and (m.get('upper_std') is not None or m.get('lower_std') is not None)
    ]

    if not testable:
        return {
            'wqi_score': None, 'category': 'Insufficient data',
            'F1': None, 'F2': None, 'F3': None,
            'n_variables': 0, 'n_failed_variables': 0,
            'n_total_tests': 0, 'n_failed_tests': 0,
            'excursion_sum': 0, 'approved_only': approved_only,
        }

    all_codes      = set(m['indicator_code'] for m in testable)
    failed_codes   = set()
    n_tests        = len(testable)
    n_failed_tests = 0
    excursion_sum  = 0.0

    for m in testable:
        val    = m['measured_val']
        upper  = m.get('upper_std')
        lower  = m.get('lower_std')

        failed  = False
        exc_val = 0.0

        if upper is not None and val > upper:
            failed  = True
            # excursion = (val / upper) - 1  [CCME F3 formula]
            exc_val = (val / upper) - 1.0 if upper != 0 else 0.0

        if lower is not None and val < lower:
            failed  = True
            exc_val = (lower / val) - 1.0 if val != 0 else 0.0

        if failed:
            n_failed_tests += 1
            failed_codes.add(m['indicator_code'])
            excursion_sum  += exc_val

    n_variables        = len(all_codes)
    n_failed_variables = len(failed_codes)

    # F1: scope — fraction of variables that fail at least once
    F1 = (n_failed_variables / n_variables) * 100.0 if n_variables else 0.0

    # F2: frequency — fraction of tests that fail
    F2 = (n_failed_tests / n_tests) * 100.0 if n_tests else 0.0

    # F3: amplitude — deviation from objectives
    nse = excursion_sum / n_tests if n_tests else 0.0
    # CCME canonical formula
    F3 = (nse / (0.01 * nse + 0.01)) * 100.0

    wqi = 100.0 - (math.sqrt(F1**2 + F2**2 + F3**2) / 1.732)
    wqi = max(0.0, min(100.0, round(wqi, 1)))

    if wqi >= 95:
        category = 'Excellent'
    elif wqi >= 80:
        category = 'Good'
    elif wqi >= 65:
        category = 'Fair'
    elif wqi >= 45:
        category = 'Marginal'
    else:
        category = 'Poor'

    return {
        'wqi_score': wqi,
        'category': category,
        'F1': round(F1, 2),
        'F2': round(F2, 2),
        'F3': round(F3, 2),
        'n_variables': n_variables,
        'n_failed_variables': n_failed_variables,
        'n_total_tests': n_tests,
        'n_failed_tests': n_failed_tests,
        'excursion_sum': round(excursion_sum, 4),
        'approved_only': approved_only,
    }


# ─── Ion Balance Error ────────────────────────────────────────────────────────

def compute_ion_balance_error(concentrations_mg_L: dict) -> dict:
    """
    Calculate charge balance error in meq/L.

    concentrations_mg_L: {indicator_code: mg_L_value}
    Missing ions are noted but treated as zero for the balance.

    Returns dict: {cations_meq, anions_meq, IBE_pct, is_good,
                   is_acceptable, missing_ions, present_ions}
    """
    cations_meq = 0.0
    anions_meq  = 0.0
    missing     = []
    present     = []

    for code, eq_wt in ION_EQ_WEIGHTS.items():
        val = concentrations_mg_L.get(code)
        ion_type = ION_TYPES.get(code, '')
        if val is None or val != val:  # None or NaN
            missing.append(code)
            continue
        meq = float(val) / eq_wt
        present.append(code)
        if ion_type == 'cation':
            cations_meq += meq
        elif ion_type == 'anion':
            anions_meq  += meq

    total = cations_meq + anions_meq
    if total == 0:
        ibe = None
        is_good = is_acceptable = None
    else:
        ibe = ((cations_meq - anions_meq) / total) * 100.0
        is_good       = abs(ibe) <= 5.0
        is_acceptable = abs(ibe) <= 10.0

    return {
        'cations_meq':   round(cations_meq, 4),
        'anions_meq':    round(anions_meq, 4),
        'IBE_pct':       round(ibe, 2) if ibe is not None else None,
        'is_good':       is_good,
        'is_acceptable': is_acceptable,
        'missing_ions':  missing,
        'present_ions':  present,
    }


# ─── Mann-Kendall Trend Test ──────────────────────────────────────────────────

def compute_mann_kendall(dates: list, values: list, alpha: float = 0.05) -> dict:
    """
    Non-parametric Mann-Kendall trend test with Sen's slope.

    dates:  list of date/datetime objects (or ISO strings)
    values: list of floats (parallel to dates)
    alpha:  significance level (default 0.05)

    Requires n >= 4.  Uses math.erfc for p-value (stdlib only).

    Returns dict: {S, variance_S, Z, p_value, trend, is_significant,
                   sen_slope_per_year, sen_intercept, n}
    """
    paired = [(d, v) for d, v in zip(dates, values) if v is not None]
    paired.sort(key=lambda x: x[0])
    n = len(paired)

    if n < 4:
        return {
            'S': None, 'variance_S': None, 'Z': None, 'p_value': None,
            'trend': 'Insufficient data', 'is_significant': False,
            'sen_slope_per_year': None, 'sen_intercept': None, 'n': n,
        }

    vals = [p[1] for p in paired]

    # Mann-Kendall S statistic
    S = 0
    for i in range(n - 1):
        for j in range(i + 1, n):
            diff = vals[j] - vals[i]
            if diff > 0:
                S += 1
            elif diff < 0:
                S -= 1

    # Tied groups correction for variance
    # Count how many times each unique value repeats
    from collections import Counter
    counts = Counter(vals)
    tie_correction = sum(tp * (tp - 1) * (2 * tp + 5) for tp in counts.values() if tp > 1)

    var_S = (n * (n - 1) * (2 * n + 5) - tie_correction) / 18.0

    if S > 0:
        Z = (S - 1) / math.sqrt(var_S)
    elif S < 0:
        Z = (S + 1) / math.sqrt(var_S)
    else:
        Z = 0.0

    # Two-tailed p-value using complementary error function (no scipy)
    p_value = math.erfc(abs(Z) / math.sqrt(2))

    if p_value <= alpha:
        if S > 0:
            trend = 'Increasing'
        elif S < 0:
            trend = 'Decreasing'
        else:
            trend = 'No trend'
        is_significant = True
    else:
        trend = 'No significant trend'
        is_significant = False

    # Sen's slope (all pair-wise slopes, median)
    slopes = []
    for i in range(n - 1):
        for j in range(i + 1, n):
            date_i = paired[i][0]
            date_j = paired[j][0]
            val_i  = paired[i][1]
            val_j  = paired[j][1]

            # Convert date diff to years
            if hasattr(date_i, 'toordinal'):
                dt_years = (date_j.toordinal() - date_i.toordinal()) / 365.25
            else:
                # ISO string fallback
                from datetime import date as _d
                di = _d.fromisoformat(str(date_i)[:10])
                dj = _d.fromisoformat(str(date_j)[:10])
                dt_years = (dj.toordinal() - di.toordinal()) / 365.25

            if dt_years != 0:
                slopes.append((val_j - val_i) / dt_years)

    slopes.sort()
    m = len(slopes)
    if m == 0:
        sen_slope = None
        sen_intercept = None
    else:
        sen_slope = slopes[m // 2] if m % 2 == 1 else (slopes[m // 2 - 1] + slopes[m // 2]) / 2.0
        # Intercept: median(val_i - slope * year_i)
        year0 = paired[0][0]
        if hasattr(year0, 'toordinal'):
            intercepts = [v - sen_slope * (paired[i][0].toordinal() / 365.25) for i, v in enumerate(vals)]
        else:
            intercepts = [v - sen_slope * (date_cls.fromisoformat(str(paired[i][0])[:10]).toordinal() / 365.25) for i, v in enumerate(vals)]
        intercepts.sort()
        k = len(intercepts)
        sen_intercept = intercepts[k // 2] if k % 2 == 1 else (intercepts[k // 2 - 1] + intercepts[k // 2]) / 2.0

    return {
        'S': S,
        'variance_S': round(var_S, 4),
        'Z': round(Z, 4),
        'p_value': round(p_value, 4),
        'trend': trend,
        'is_significant': is_significant,
        'sen_slope_per_year': round(sen_slope, 6) if sen_slope is not None else None,
        'sen_intercept': round(sen_intercept, 4) if sen_intercept is not None else None,
        'n': n,
    }


# ─── Langelier Saturation Index ───────────────────────────────────────────────

def compute_lsi(pH: float, temperature_C: float, tds_mg_L: float,
                calcium_mg_L: float, alkalinity_mgCaCO3_L: float) -> dict:
    """
    Langelier Saturation Index (LSI) and Ryznar Stability Index (RSI).

    LSI = pH_measured - pH_saturation
    RSI = 2 * pHs - pH
    pHs = (9.3 + A + B) - (C + D)

    All inputs must be numeric.

    Returns dict: {pHs, LSI, RSI, lsi_class, rsi_class}
    """
    # A: temperature factor
    A = (math.log10(temperature_C + 273) * (-13.12)) + 34.55

    # B: TDS factor
    if tds_mg_L > 0:
        B = math.log10(tds_mg_L) - 1.0
    else:
        B = 0.0

    # C: calcium hardness as CaCO3 factor
    # CaCO3 hardness = calcium_mg_L * (100.09/40.08) ≈ * 2.497
    ca_hardness = calcium_mg_L * 2.497
    if ca_hardness > 0:
        C = math.log10(ca_hardness)
    else:
        C = 0.0

    # D: alkalinity factor
    if alkalinity_mgCaCO3_L > 0:
        D = math.log10(alkalinity_mgCaCO3_L)
    else:
        D = 0.0

    pHs = (9.3 + A + B) - (C + D)
    LSI = pH - pHs
    RSI = 2.0 * pHs - pH

    # LSI interpretation
    if LSI > 0.5:
        lsi_class = 'Scale-forming (oversaturated)'
    elif LSI > 0.0:
        lsi_class = 'Slightly scale-forming'
    elif LSI == 0.0:
        lsi_class = 'Stable / balanced'
    elif LSI >= -0.5:
        lsi_class = 'Slightly corrosive'
    else:
        lsi_class = 'Corrosive (undersaturated)'

    # RSI interpretation
    if RSI < 5.5:
        rsi_class = 'Heavy scale-forming'
    elif RSI < 6.2:
        rsi_class = 'Scale-forming'
    elif RSI < 6.8:
        rsi_class = 'Slightly scale-forming'
    elif RSI < 7.5:
        rsi_class = 'Stable'
    elif RSI < 8.0:
        rsi_class = 'Slightly corrosive'
    elif RSI < 9.0:
        rsi_class = 'Corrosive'
    else:
        rsi_class = 'Highly corrosive'

    return {
        'pHs': round(pHs, 3),
        'LSI': round(LSI, 3),
        'RSI': round(RSI, 3),
        'lsi_class': lsi_class,
        'rsi_class': rsi_class,
        'A': round(A, 4), 'B': round(B, 4), 'C': round(C, 4), 'D': round(D, 4),
    }


# ─── Carlson Trophic State Index ──────────────────────────────────────────────

def compute_trophic_state_index(tp_ug_L=None, chl_a_ug_L=None, secchi_m=None) -> dict:
    """
    Carlson (1977) Trophic State Index.

    All parameters are optional but at least one must be provided.
    TSI scale: <40=Oligotrophic, 40–50=Mesotrophic, 50–70=Eutrophic, >70=Hypereutrophic

    Returns dict: {tsi_tp, tsi_chl, tsi_sd, tsi_overall, trophic_class,
                   is_eutrophic, is_hypereutrophic}
    """
    tsi_tp  = None
    tsi_chl = None
    tsi_sd  = None

    if tp_ug_L is not None and tp_ug_L > 0:
        tsi_tp = 14.42 * math.log(tp_ug_L) + 4.15

    if chl_a_ug_L is not None and chl_a_ug_L > 0:
        tsi_chl = 30.6 + 9.81 * math.log(chl_a_ug_L)

    if secchi_m is not None and secchi_m > 0:
        tsi_sd = 60.0 - 14.41 * math.log(secchi_m)

    components = [v for v in [tsi_tp, tsi_chl, tsi_sd] if v is not None]
    tsi_overall = round(sum(components) / len(components), 1) if components else None

    if tsi_overall is None:
        trophic_class = 'Insufficient data'
        is_eutrophic  = None
        is_hyper      = None
    elif tsi_overall < 40:
        trophic_class = 'Oligotrophic'
        is_eutrophic  = False
        is_hyper      = False
    elif tsi_overall < 50:
        trophic_class = 'Mesotrophic'
        is_eutrophic  = False
        is_hyper      = False
    elif tsi_overall < 70:
        trophic_class = 'Eutrophic'
        is_eutrophic  = True
        is_hyper      = False
    else:
        trophic_class = 'Hypereutrophic'
        is_eutrophic  = True
        is_hyper      = True

    return {
        'tsi_tp':           round(tsi_tp, 1)  if tsi_tp  is not None else None,
        'tsi_chl':          round(tsi_chl, 1) if tsi_chl is not None else None,
        'tsi_sd':           round(tsi_sd, 1)  if tsi_sd  is not None else None,
        'tsi_overall':      tsi_overall,
        'trophic_class':    trophic_class,
        'is_eutrophic':     is_eutrophic,
        'is_hypereutrophic': is_hyper,
    }


# ─── Piper Diagram Data ───────────────────────────────────────────────────────

def compute_piper_data(concentrations_mg_L: dict) -> dict:
    """
    Compute Piper trilinear diagram coordinates from major ion concentrations.

    Input keys: CA, MG, NA, K, HCO3, CO3, CL, SO4  (mg/L)
    All missing values are treated as zero.

    Returns dict: {
        pct_Ca, pct_Mg, pct_NaK,          # cation ternary (sum to 100)
        pct_Cl, pct_SO4, pct_HCO3,        # anion ternary (sum to 100)
        x_diamond, y_diamond,              # central diamond coordinates [0-100]
        water_type, cations_meq, anions_meq
    }
    """
    ca_meq   = ion_to_meq('CA',   concentrations_mg_L.get('CA',   0))
    mg_meq   = ion_to_meq('MG',   concentrations_mg_L.get('MG',   0))
    na_meq   = ion_to_meq('NA',   concentrations_mg_L.get('NA',   0))
    k_meq    = ion_to_meq('K',    concentrations_mg_L.get('K',    0))
    hco3_meq = ion_to_meq('HCO3', concentrations_mg_L.get('HCO3', 0))
    co3_meq  = ion_to_meq('CO3',  concentrations_mg_L.get('CO3',  0))
    cl_meq   = ion_to_meq('CL',   concentrations_mg_L.get('CL',   0))
    so4_meq  = ion_to_meq('SO4',  concentrations_mg_L.get('SO4',  0))

    nak_meq   = na_meq + k_meq
    hco3_tot  = hco3_meq + co3_meq  # combined carbonate alkalinity

    sum_cat = ca_meq + mg_meq + nak_meq
    sum_an  = cl_meq + so4_meq + hco3_tot

    if sum_cat == 0:
        pct_Ca = pct_Mg = pct_NaK = 0.0
    else:
        pct_Ca  = ca_meq  / sum_cat * 100.0
        pct_Mg  = mg_meq  / sum_cat * 100.0
        pct_NaK = nak_meq / sum_cat * 100.0

    if sum_an == 0:
        pct_Cl = pct_SO4 = pct_HCO3 = 0.0
    else:
        pct_Cl   = cl_meq    / sum_an * 100.0
        pct_SO4  = so4_meq   / sum_an * 100.0
        pct_HCO3 = hco3_tot  / sum_an * 100.0

    # Central diamond: x = pct_Cl + pct_SO4 (anion side projected)
    # y = pct_Ca + pct_Mg (cation side projected)
    x_diamond = pct_Cl + pct_SO4
    y_diamond  = pct_Ca + pct_Mg

    # Simplified water type classification
    if pct_NaK >= 50 and pct_HCO3 >= 50:
        water_type = 'Na-HCO₃ (Sodium Bicarbonate)'
    elif pct_NaK >= 50 and pct_Cl >= 50:
        water_type = 'Na-Cl (Sodium Chloride)'
    elif pct_NaK >= 50 and pct_SO4 >= 50:
        water_type = 'Na-SO₄ (Sodium Sulphate)'
    elif (pct_Ca + pct_Mg) >= 50 and pct_HCO3 >= 50:
        water_type = 'Ca-Mg-HCO₃ (Calcium Bicarbonate)'
    elif (pct_Ca + pct_Mg) >= 50 and pct_SO4 >= 50:
        water_type = 'Ca-SO₄ (Calcium Sulphate)'
    elif (pct_Ca + pct_Mg) >= 50 and pct_Cl >= 50:
        water_type = 'Ca-Cl (Calcium Chloride)'
    else:
        water_type = 'Mixed / No dominant type'

    return {
        'pct_Ca':   round(pct_Ca,  1),
        'pct_Mg':   round(pct_Mg,  1),
        'pct_NaK':  round(pct_NaK, 1),
        'pct_Cl':   round(pct_Cl,  1),
        'pct_SO4':  round(pct_SO4, 1),
        'pct_HCO3': round(pct_HCO3,1),
        'x_diamond': round(x_diamond, 1),
        'y_diamond': round(y_diamond, 1),
        'water_type': water_type,
        'cations_meq': round(sum_cat, 4),
        'anions_meq':  round(sum_an, 4),
    }


# ─── Stiff Diagram Data ───────────────────────────────────────────────────────

def compute_stiff_data(concentrations_mg_L: dict, label: str = '') -> dict:
    """
    Build Stiff diagram polygon data (meq/L per arm pair).

    Ion arm pairs (left = cations, right = anions):
      Arm 1: Na+K  vs  Cl
      Arm 2: Ca    vs  SO4
      Arm 3: Mg    vs  HCO3+CO3

    Returns dict: {label, arms: [{cation, anion, cat_meq, an_meq}], max_meq}
    """
    arms = [
        {
            'cation':  'Na+K',
            'anion':   'Cl',
            'cat_meq': round(ion_to_meq('NA', concentrations_mg_L.get('NA', 0))
                           + ion_to_meq('K',  concentrations_mg_L.get('K', 0)), 3),
            'an_meq':  round(ion_to_meq('CL', concentrations_mg_L.get('CL', 0)), 3),
        },
        {
            'cation':  'Ca',
            'anion':   'SO4',
            'cat_meq': round(ion_to_meq('CA',  concentrations_mg_L.get('CA', 0)), 3),
            'an_meq':  round(ion_to_meq('SO4', concentrations_mg_L.get('SO4', 0)), 3),
        },
        {
            'cation':  'Mg',
            'anion':   'HCO3+CO3',
            'cat_meq': round(ion_to_meq('MG',  concentrations_mg_L.get('MG', 0)), 3),
            'an_meq':  round(ion_to_meq('HCO3', concentrations_mg_L.get('HCO3', 0))
                           + ion_to_meq('CO3',  concentrations_mg_L.get('CO3', 0)), 3),
        },
    ]

    all_vals = [a['cat_meq'] for a in arms] + [a['an_meq'] for a in arms]
    max_meq  = max(all_vals) if all_vals else 1.0

    return {
        'label':   label,
        'arms':    arms,
        'max_meq': round(max_meq, 3),
    }


# ─── Blue Drop Score ──────────────────────────────────────────────────────────

def compute_blue_drop_score(compliance_by_category: dict) -> dict:
    """
    Compute Blue Drop Programme weighted score.

    compliance_by_category: {
        'microbiological':    float (0-100, % of compliant tests)
        'chemical_health':    float
        'chemical_aesthetic': float
        'physical':           float
    }
    Any missing category is excluded from the weighted average.

    Returns dict: {overall_score, grade, breakdown, achieves_blue_drop}
    """
    weighted_sum  = 0.0
    total_weight  = 0.0
    breakdown     = {}

    for cat, weight in BLUE_DROP_WEIGHTS.items():
        score = compliance_by_category.get(cat)
        if score is not None:
            weighted_score = score * weight
            weighted_sum  += weighted_score
            total_weight  += weight
            breakdown[cat] = {
                'score':          round(score, 1),
                'weight':         weight,
                'weighted_score': round(weighted_score, 2),
            }

    if total_weight == 0:
        return {
            'overall_score': None, 'grade': 'Insufficient data',
            'breakdown': breakdown, 'achieves_blue_drop': False,
        }

    overall = (weighted_sum / total_weight) if total_weight > 0 else 0.0
    overall = round(overall, 1)

    if overall >= 95:
        grade = 'Blue Drop'
    elif overall >= 85:
        grade = 'Excellent'
    elif overall >= 75:
        grade = 'Good'
    elif overall >= 60:
        grade = 'Satisfactory'
    else:
        grade = 'Below Standard'

    return {
        'overall_score':    overall,
        'grade':            grade,
        'breakdown':        breakdown,
        'achieves_blue_drop': overall >= 95.0,
    }


# ─── Irrigation Suitability (DWAF Vol 4, 1996) ────────────────────────────────

def compute_sar(concentrations_mg_L: dict) -> dict:
    """
    Sodium Adsorption Ratio: SAR = Na(meq/L) / sqrt((Ca(meq/L)+Mg(meq/L))/2).
    Input keys: NA, CA, MG (mg/L). Returns {sar, na_meq, ca_meq, mg_meq};
    sar is None if Ca+Mg meq sum is 0 (cannot divide by zero).
    """
    na_meq = ion_to_meq('NA', concentrations_mg_L.get('NA'))
    ca_meq = ion_to_meq('CA', concentrations_mg_L.get('CA'))
    mg_meq = ion_to_meq('MG', concentrations_mg_L.get('MG'))
    denom = (ca_meq + mg_meq) / 2.0
    sar = round(na_meq / math.sqrt(denom), 2) if denom > 0 else None
    return {
        'sar':    sar,
        'na_meq': round(na_meq, 4),
        'ca_meq': round(ca_meq, 4),
        'mg_meq': round(mg_meq, 4),
    }


def classify_irrigation_sar(sar) -> dict:
    """DWAF Vol 4 SAR bands: <=2.0 / 2.0-8.0 / 8.0-15.0 / >15.0."""
    if sar is None:
        return {'band': None, 'effect_description': 'Insufficient data (Na/Ca/Mg) to compute SAR.'}
    if sar <= 2.0:
        return {'band': '<=2.0', 'effect_description': 'No significant sodium-related restriction on crop yield or soil structure.'}
    if sar <= 8.0:
        return {'band': '2.0-8.0', 'effect_description': 'Slight to moderate risk of sodium-related soil structure degradation for sodium-sensitive crops.'}
    if sar <= 15.0:
        return {'band': '8.0-15.0', 'effect_description': 'Moderate to severe sodium hazard — soil permeability and crop yield may be affected, particularly for sensitive crops.'}
    return {'band': '>15.0', 'effect_description': 'Severe sodium hazard — significant risk of soil structure breakdown and reduced crop yield.'}


def classify_irrigation_ec(ec_mS_m) -> dict:
    """DWAF Vol 4 EC bands (mS/m): <=40 / 40-90 / 90-270 / 270-540 / >540."""
    if ec_mS_m is None:
        return {'band': None, 'relative_yield_pct': None, 'management_note': 'No EC measurement available.'}
    if ec_mS_m <= 40:
        return {'band': '<=40', 'relative_yield_pct': 100, 'management_note': 'No restriction on crop yield.'}
    if ec_mS_m <= 90:
        return {'band': '40-90', 'relative_yield_pct': 95, 'management_note': 'Slight yield reduction possible for sensitive crops.'}
    if ec_mS_m <= 270:
        return {'band': '90-270', 'relative_yield_pct': 90, 'management_note': 'Moderate yield reduction; salt-tolerant crops recommended.'}
    if ec_mS_m <= 540:
        return {'band': '270-540', 'relative_yield_pct': 80, 'management_note': 'Significant yield reduction; high-frequency irrigation required to manage salinity.'}
    return {'band': '>540', 'relative_yield_pct': None, 'management_note': 'Usable only for very salt-tolerant crops under careful management; increasingly restrictive.'}


_SAR_BAND_ORDER = ['<=2.0', '2.0-8.0', '8.0-15.0', '>15.0']
_EC_BAND_ORDER   = ['<=40', '40-90', '90-270', '270-540', '>540']


def compute_irrigation_suitability(concentrations_mg_L: dict, ec_mS_m=None) -> dict:
    """Combines compute_sar + classify_irrigation_sar + classify_irrigation_ec.
    overall_restriction_class is the worse of the two axes: 'none' < 'slight_moderate' < 'severe'."""
    sar_result = compute_sar(concentrations_mg_L)
    sar_class  = classify_irrigation_sar(sar_result['sar'])
    ec_class   = classify_irrigation_ec(ec_mS_m)

    sar_rank = _SAR_BAND_ORDER.index(sar_class['band']) if sar_class['band'] in _SAR_BAND_ORDER else -1
    ec_rank  = _EC_BAND_ORDER.index(ec_class['band'])   if ec_class['band']  in _EC_BAND_ORDER  else -1
    worst = max(sar_rank, ec_rank)

    if worst <= 0:
        overall_restriction_class = 'none'
    elif worst == 1:
        overall_restriction_class = 'slight_moderate'
    else:
        overall_restriction_class = 'severe'

    return {
        'sar_result': sar_result,
        'sar_class':  sar_class,
        'ec_class':   ec_class,
        'overall_restriction_class': overall_restriction_class,
    }


# ─── Livestock Watering Suitability (DWAF Vol 5, 1996) ────────────────────────

def compute_livestock_suitability(tds_mg_L, bands: list) -> dict:
    """
    bands: rows fetched by the caller from WQ_Livestock_TDS_Bands, each a dict
    with species/tds_min_mgL/tds_max_mgL/severity_rating/band_label. Kept pure
    (no DB access) — DB fetch is the caller's responsibility.
    Returns {by_species: {species: {severity_rating, band_label}},
             most_restrictive_species, most_restrictive_rating}.
    """
    if tds_mg_L is None:
        return {'by_species': {}, 'most_restrictive_species': None, 'most_restrictive_rating': None}

    by_species = {}
    for b in bands:
        lo = b.get('tds_min_mgL') or 0
        hi = b.get('tds_max_mgL')
        if tds_mg_L >= lo and (hi is None or tds_mg_L < hi):
            sp = b['species']
            if sp not in by_species:
                by_species[sp] = {
                    'severity_rating': b['severity_rating'],
                    'band_label':      b['band_label'],
                }

    if not by_species:
        return {'by_species': {}, 'most_restrictive_species': None, 'most_restrictive_rating': None}

    most_sp = max(by_species.items(), key=lambda kv: kv[1]['severity_rating'])
    return {
        'by_species': by_species,
        'most_restrictive_species': most_sp[0],
        'most_restrictive_rating':  most_sp[1]['severity_rating'],
    }


# ─── Aquaculture Suitability (DWAF Vol 6, 1996) ───────────────────────────────

def classify_hardness(hardness_val) -> str:
    """Soft <60 / Medium 60-119 / Hard 120-180 / Very Hard >180 mg CaCO3/L.
    Defaults to 'medium' if hardness wasn't measured (same convention as the
    TWQR hardness-dependent dispatch elsewhere in this codebase)."""
    if hardness_val is None:
        return 'medium'
    if hardness_val < 60:
        return 'soft'
    if hardness_val < 120:
        return 'medium'
    if hardness_val <= 180:
        return 'hard'
    return 'very_hard'


def compute_aquaculture_suitability(measurements: dict, hardness_val, criteria_rows: list) -> dict:
    """
    measurements: {indicator_code: measured_val} in each indicator's own
    stored unit (matches WQ_Aquaculture_Criteria.unit per row).
    criteria_rows: rows fetched by the caller from WQ_Aquaculture_Criteria.
    Cadmium ('CD') rows carry a hardness_class and are only evaluated when it
    matches classify_hardness(hardness_val) — mirrors the TWQR hardness-band
    dispatch pattern used elsewhere.
    Returns {per_indicator: [...], overall_flag: 'suitable'|'caution'|'unsuitable', hardness_class}.
    """
    hclass = classify_hardness(hardness_val)
    per_indicator = []
    violations = 0

    for row in criteria_rows:
        code = row['indicator_code']
        if row.get('hardness_class') and row['hardness_class'] != hclass:
            continue
        val = measurements.get(code)
        if val is None:
            continue
        val = float(val)
        lower = row.get('twqr_lower')
        upper = row.get('twqr_upper')
        status = 'within'
        if lower is not None and val < lower:
            status = 'below'
        if upper is not None and val > upper:
            status = 'above'
        if status != 'within':
            violations += 1
        per_indicator.append({
            'indicator_code': code,
            'measured_val':   val,
            'twqr_lower':     lower,
            'twqr_upper':     upper,
            'unit':           row.get('unit'),
            'status':         status,
            'note':           row.get('note'),
        })

    if violations == 0:
        overall_flag = 'suitable'
    elif violations <= 2:
        overall_flag = 'caution'
    else:
        overall_flag = 'unsuitable'

    return {'per_indicator': per_indicator, 'overall_flag': overall_flag, 'hardness_class': hclass}


# ─── Acid Mine Drainage flagging (single source of truth) ────────────────────
# Extracted verbatim from the logic previously inline in wq_bp.analytics_amd()
# so that endpoint and the diagnostic engine below share one implementation.
AMD_FLAG_THRESHOLDS = {
    'PH':  ('<=', 4.0,    'Acidic — AMD indicator'),
    'EC':  ('>=', 500.0,  'Very high EC — AMD indicator'),
    'SO4': ('>=', 1000.0, 'High sulphate — AMD indicator'),
    'FE':  ('>=', 10.0,   'Elevated iron — AMD indicator'),
}


def compute_amd_flags(concentrations_mg_L: dict) -> dict:
    """SA Witwatersrand Goldfields baseline AMD flagging. Returns
    {flags: [...], amd_risk: 'High'|'Moderate'|'Low'|'None', is_amd_suspect}."""
    flags = []
    for code, (op, threshold, desc) in AMD_FLAG_THRESHOLDS.items():
        v = concentrations_mg_L.get(code)
        if v is None:
            continue
        if op == '<=' and v <= threshold:
            flags.append({'indicator': code, 'value': v, 'threshold': threshold, 'note': desc})
        elif op == '>=' and v >= threshold:
            flags.append({'indicator': code, 'value': v, 'threshold': threshold, 'note': desc})

    amd_risk = 'High' if len(flags) >= 3 else ('Moderate' if len(flags) >= 2 else ('Low' if len(flags) >= 1 else 'None'))
    return {'flags': flags, 'amd_risk': amd_risk, 'is_amd_suspect': len(flags) >= 2}


# ─── Temporal stability (geogenic-signature support) ──────────────────────────

def compute_temporal_stability(values: list) -> dict:
    """
    Lightweight coefficient-of-variation stability check for a station's
    historical readings of one indicator. Used by the geogenic contamination
    signature to distinguish a stable natural baseline from a recent
    contamination event. Returns {is_stable, cv_pct, n, method}.
    """
    vals = [float(v) for v in values if v is not None]
    n = len(vals)
    if n < 2:
        return {'is_stable': None, 'cv_pct': None, 'n': n, 'method': 'insufficient_data'}

    mean = sum(vals) / n
    if mean == 0:
        return {'is_stable': None, 'cv_pct': None, 'n': n, 'method': 'insufficient_data'}

    variance = sum((v - mean) ** 2 for v in vals) / n
    cv_pct = round((math.sqrt(variance) / mean) * 100, 1)
    return {'is_stable': cv_pct < 20.0, 'cv_pct': cv_pct, 'n': n, 'method': 'coefficient_of_variation'}


# ─── Contamination Source-Attribution Engine ──────────────────────────────────
# Weight-of-Evidence style scoring. Each signature function returns
# (points, max_points, matched_signals, contradicting_signals, contextual_modifiers)
# where points/max_points only reflects signals that were actually evaluable
# for this reading (missing data never counts against or for a hypothesis).
# Contextual modifiers add their weight to BOTH points and max_points when
# they fire, which mathematically raises the confidence ratio without ever
# letting it exceed 100%.

def _signature_amd(m: dict, ctx: dict):
    matched, contra, modifiers = [], [], []
    points = 0.0
    max_points = 0.0

    amd = compute_amd_flags(m)
    flagged = {f['indicator']: f for f in amd['flags']}
    weight_map = {'PH': 30, 'SO4': 30, 'FE': 20, 'EC': 20}
    for code in ('PH', 'SO4', 'FE', 'EC'):
        if m.get(code) is None:
            continue
        w = weight_map[code]
        max_points += w
        if code in flagged:
            f = flagged[code]
            points += w
            matched.append({'signal': code, 'weight': w,
                             'detail': f"{f['note']} ({f['value']} vs threshold {f['threshold']})"})
        else:
            contra.append({'signal': code, 'detail': f"{code} value ({m.get(code)}) not in AMD-suspect range"})

    for code, label, thresh in (('CD', 'Cadmium', 0.01), ('ZN', 'Zinc', 1.0),
                                 ('CU', 'Copper', 0.5), ('NI', 'Nickel', 0.5)):
        val = m.get(code)
        if val is None:
            continue
        max_points += 10
        if val >= thresh:
            points += 10
            matched.append({'signal': code, 'weight': 10,
                             'detail': f'{label} elevated ({val}), consistent with metal mobilisation from acid mine drainage.'})

    hard_matched = any(s['signal'] in ('PH', 'SO4') for s in matched)
    if hard_matched:
        if ctx.get('aquifer_type') == 'confined':
            points += 15
            max_points += 15
            modifiers.append({'modifier': 'confined_aquifer', 'weight': 15,
                'detail': "This station's confined aquifer classification increases the likelihood of a point-source breach (e.g. an old mine shaft or failed borehole casing) over diffuse surface pollution."})
        elif ctx.get('depth_m') is not None and ctx['depth_m'] >= 50:
            points += 15
            max_points += 15
            modifiers.append({'modifier': 'deep_station', 'weight': 15,
                'detail': f"This station's depth ({ctx['depth_m']}m) makes a point-source breach a more likely explanation than diffuse surface pollution."})

    return points, max_points, matched, contra, modifiers


def _signature_sewage(m: dict, ctx: dict):
    matched, contra = [], []
    points = 0.0
    max_points = 0.0

    ecoli = m.get('ECOLI')
    if ecoli is not None:
        max_points += 30
        if ecoli > 0:
            points += 30
            matched.append({'signal': 'ECOLI', 'weight': 30, 'detail': f'E. coli detected ({ecoli} CFU/100mL) — a direct indicator of fecal/sewage contamination.'})
        else:
            contra.append({'signal': 'ECOLI', 'detail': 'No E. coli detected.'})

    tcol = m.get('TCOL')
    if tcol is not None:
        max_points += 20
        if tcol > 0:
            points += 20
            matched.append({'signal': 'TCOL', 'weight': 20, 'detail': f'Total coliforms detected ({tcol} CFU/100mL), consistent with sewage/wastewater contamination.'})
        else:
            contra.append({'signal': 'TCOL', 'detail': 'No total coliforms detected.'})

    nh4 = m.get('NH4')
    if nh4 is not None:
        max_points += 20
        if nh4 >= 1.5:
            points += 20
            matched.append({'signal': 'NH4', 'weight': 20, 'detail': f'Ammonia elevated ({nh4} mg/L), consistent with untreated sewage/wastewater.'})
        else:
            contra.append({'signal': 'NH4', 'detail': f'Ammonia ({nh4} mg/L) not elevated.'})

    tp = m.get('TP')
    if tp is not None:
        max_points += 10
        if tp >= 100:
            points += 10
            matched.append({'signal': 'TP', 'weight': 10, 'detail': f'Total phosphorus elevated ({tp} µg/L), consistent with sewage/wastewater nutrient loading.'})

    return points, max_points, matched, contra, []


def _signature_agri_runoff(m: dict, ctx: dict):
    matched, contra = [], []
    points = 0.0
    max_points = 0.0

    no3 = m.get('NO3')
    if no3 is not None:
        max_points += 30
        if no3 >= 6.0:
            points += 30
            matched.append({'signal': 'NO3', 'weight': 30, 'detail': f'Nitrate elevated ({no3} mg/L), consistent with fertiliser/agricultural runoff.'})
        else:
            contra.append({'signal': 'NO3', 'detail': f'Nitrate ({no3} mg/L) not elevated.'})

    tp = m.get('TP')
    if tp is not None:
        max_points += 20
        if tp >= 100:
            points += 20
            matched.append({'signal': 'TP', 'weight': 20, 'detail': f'Total phosphorus elevated ({tp} µg/L), consistent with fertiliser runoff.'})

    season = ctx.get('season')
    if season:
        max_points += 10
        if season == 'Wet':
            points += 10
            matched.append({'signal': 'season', 'weight': 10, 'detail': 'Sample taken in the wet season, consistent with rainfall-driven agricultural runoff.'})
        else:
            contra.append({'signal': 'season', 'detail': 'Sample taken in the dry season, less consistent with rainfall-driven runoff.'})

    ecoli = m.get('ECOLI')
    if ecoli is not None:
        max_points += 10
        if ecoli == 0:
            points += 10
            matched.append({'signal': 'ECOLI absence', 'weight': 10, 'detail': 'No E. coli detected, consistent with agricultural chemical runoff rather than sewage.'})
        else:
            contra.append({'signal': 'ECOLI', 'detail': 'E. coli present — more consistent with sewage than pure agricultural runoff.'})

    return points, max_points, matched, contra, []


def _signature_landfill_leachate(m: dict, ctx: dict):
    matched, contra = [], []
    points = 0.0
    max_points = 0.0

    nh4 = m.get('NH4')
    if nh4 is not None:
        max_points += 30
        if nh4 >= 1.5:
            points += 30
            matched.append({'signal': 'NH4', 'weight': 30, 'detail': f'Ammonia elevated ({nh4} mg/L), consistent with landfill leachate.'})
        else:
            contra.append({'signal': 'NH4', 'detail': f'Ammonia ({nh4} mg/L) not elevated.'})

    cl = m.get('CL')
    if cl is not None:
        max_points += 20
        if cl >= 100:
            points += 20
            matched.append({'signal': 'CL', 'weight': 20, 'detail': f'Chloride elevated ({cl} mg/L), consistent with landfill leachate.'})
        else:
            contra.append({'signal': 'CL', 'detail': f'Chloride ({cl} mg/L) not elevated.'})

    return points, max_points, matched, contra, []


def _signature_saline_intrusion(m: dict, ctx: dict):
    matched, contra, modifiers = [], [], []
    points = 0.0
    max_points = 0.0

    cl = m.get('CL')
    na = m.get('NA')
    br = m.get('BR')

    if cl is not None:
        max_points += 30
        if cl > 200:
            points += 30
            matched.append({'signal': 'CL', 'weight': 30, 'detail': f'Chloride elevated ({cl} mg/L, > 200 mg/L saline-intrusion threshold).'})
        else:
            contra.append({'signal': 'CL', 'detail': f'Chloride ({cl} mg/L) below the saline-intrusion threshold.'})

    if cl is not None and na is not None:
        cl_meq = ion_to_meq('CL', cl)
        na_meq = ion_to_meq('NA', na)
        if cl_meq > 0:
            max_points += 20
            ratio = na_meq / cl_meq
            if ratio < 0.86:
                points += 20
                matched.append({'signal': 'Na/Cl ratio', 'weight': 20, 'detail': f'Na/Cl molar ratio ({ratio:.2f}) below 0.86, consistent with a seawater/saline-intrusion signature.'})
            else:
                contra.append({'signal': 'Na/Cl ratio', 'detail': f'Na/Cl molar ratio ({ratio:.2f}) not consistent with seawater intrusion.'})

    if br is not None and br > 0 and cl is not None:
        max_points += 10
        cl_br_ratio = cl / br
        if 250 <= cl_br_ratio <= 400:
            points += 10
            modifiers.append({'modifier': 'cl_br_ratio', 'weight': 10,
                'detail': f'Cl/Br mass ratio ({cl_br_ratio:.0f}) close to the seawater signature (~297), supporting saline intrusion.'})
        else:
            matched.append({'signal': 'Cl/Br ratio', 'weight': 0,
                'detail': f'Cl/Br ratio ({cl_br_ratio:.0f}) measured but not a simple seawater signature — may indicate evaporite dissolution or an anthropogenic chloride source.'})

    return points, max_points, matched, contra, modifiers


def _signature_geogenic(m: dict, ctx: dict):
    matched, contra = [], []
    points = 0.0
    max_points = 0.0

    stability = ctx.get('historical_stability') or {}
    for code in ('FE', 'MN', 'FL', 'EC'):
        st = stability.get(code)
        if not st or st.get('is_stable') is None:
            continue
        max_points += 15
        if st['is_stable']:
            points += 15
            matched.append({'signal': f'{code} stability', 'weight': 15,
                'detail': f'{code} concentration stable over time (CV {st.get("cv_pct")}%), consistent with a natural/geogenic background rather than a recent contamination event.'})
        else:
            contra.append({'signal': f'{code} stability', 'detail': f'{code} shows an unstable/trending concentration, less consistent with a steady geogenic background.'})

    ecoli = m.get('ECOLI')
    tcol = m.get('TCOL')
    nh4 = m.get('NH4')
    any_measured = any(v is not None for v in (ecoli, tcol, nh4))
    if any_measured:
        max_points += 10
        anthro_present = (ecoli is not None and ecoli > 0) or (tcol is not None and tcol > 0) or (nh4 is not None and nh4 >= 1.5)
        if not anthro_present:
            points += 10
            matched.append({'signal': 'no anthropogenic co-signals', 'weight': 10,
                'detail': 'No elevated ammonia or fecal bacteria detected, consistent with a natural/geogenic source rather than anthropogenic pollution.'})
        else:
            contra.append({'signal': 'anthropogenic co-signals present', 'detail': 'Elevated ammonia or fecal bacteria detected, inconsistent with a purely natural/geogenic source.'})

    return points, max_points, matched, contra, []


_CONTAMINATION_SIGNATURE_FUNCS = {
    'AMD':               ('Acid Mine Drainage',              _signature_amd),
    'SEWAGE':            ('Sewage / Domestic Wastewater',    _signature_sewage),
    'AGRI_RUNOFF':       ('Agricultural / Fertiliser Runoff', _signature_agri_runoff),
    'LANDFILL_LEACHATE': ('Landfill Leachate',                _signature_landfill_leachate),
    'SALINE_INTRUSION':  ('Saline / Seawater Intrusion',      _signature_saline_intrusion),
    'GEOGENIC':          ('Natural / Geogenic Background',    _signature_geogenic),
}

CONTAMINATION_SIGNATURES = _CONTAMINATION_SIGNATURE_FUNCS  # public alias, for callers that want the registry


def diagnose_contamination_source(measurements_mg_L: dict, context: dict = None) -> dict:
    """
    measurements_mg_L: {indicator_code: value} for THIS reading, in each
    indicator's own stored unit.
    context (all optional — the engine runs fully without any of them):
        season: 'Wet'|'Dry'|None
        aquifer_type: 'unconfined'|'semi-confined'|'confined'|None
        depth_m: float|None
        historical_stability: {indicator_code: compute_temporal_stability(...) result}

    Weight-of-Evidence scoring: each signature accumulates points only from
    signals that were actually measured for this reading; a contradicting
    signal subtracts 20 points (clamped to [0, max_points] before the ratio
    is taken); a contextual modifier (e.g. confined/deep aquifer + an AMD
    match) adds its weight to both points and max_points, which raises the
    confidence ratio without ever letting it exceed 100%.

    Returns {candidates: [{source_code, source_label, confidence_pct,
    matched_signals, contradicting_signals, contextual_modifiers}, ...]
    ranked descending by confidence_pct, engine_version: 'v1'}.
    """
    ctx = context or {}
    candidates = []

    for code, (label, func) in _CONTAMINATION_SIGNATURE_FUNCS.items():
        points, max_points, matched, contra, modifiers = func(measurements_mg_L, ctx)
        if max_points <= 0:
            continue  # no evaluable signals at all for this reading/signature

        points -= 20.0 * len(contra)
        points = max(0.0, min(points, max_points))
        confidence_pct = round(100.0 * points / max_points, 1)

        candidates.append({
            'source_code':           code,
            'source_label':          label,
            'confidence_pct':        confidence_pct,
            'matched_signals':       matched,
            'contradicting_signals': contra,
            'contextual_modifiers':  modifiers,
        })

    candidates.sort(key=lambda c: c['confidence_pct'], reverse=True)
    return {'candidates': candidates, 'engine_version': 'v1'}


def explain_diagnostic_finding(candidate: dict) -> str:
    """
    Pure deterministic string templating (NOT an LLM call) — turns one
    candidate dict (as returned inside diagnose_contamination_source's
    'candidates' list) into a plain-language sentence for end users.
    """
    label = candidate['source_label']
    conf = candidate['confidence_pct']
    parts = [f"Possible {label} ({conf}% confidence):"]

    detail_bits = [s['detail'] for s in candidate.get('matched_signals', []) if s.get('detail')]
    if detail_bits:
        parts.append(' '.join(d if d.endswith('.') else d + '.' for d in detail_bits))

    modifiers = candidate.get('contextual_modifiers') or []
    mod_bits = [m['detail'] for m in modifiers if m.get('detail')]
    if mod_bits:
        parts.append('Contextual factor: ' + ' '.join(mod_bits))

    return ' '.join(parts)


# ─── Aquatic Ecosystem Health Score ────────────────────────────────────────────

def compute_ecosystem_health_score(measurements: list) -> dict:
    """
    measurements: list of dicts, each carrying at least:
        indicator_code, indicator_name, measured_val,
        twqr_lower, twqr_upper, twqr_cev, twqr_aev, twqr_basis, is_compliant_twqr
    (the caller is responsible for resolving hardness-dependent CEV/AEV per
    reading before calling this, same as the existing TWQR compliance path).

    Per-indicator tier scoring (only for twqr_basis not in (None, 'not_applicable')):
        within TWQR           -> 100
        between TWQR and CEV  ->  60
        between CEV and AEV   ->  25
        beyond AEV            ->   0
        (indicators lacking cev/aev: binary is_compliant_twqr ? 100 : 0)
    overall_score = mean of per-indicator scores.
    Grade bands: >=90 Excellent / 75-89 Good / 50-74 Fair / 25-49 Poor / <25 Critical.
    """
    breakdown = []
    total = 0.0
    n = 0

    for m in measurements:
        basis = m.get('twqr_basis')
        if basis in (None, 'not_applicable'):
            continue
        val = m.get('measured_val')
        if val is None:
            continue

        cev = m.get('twqr_cev')
        aev = m.get('twqr_aev')
        upper = m.get('twqr_upper')
        compliant = m.get('is_compliant_twqr')

        score = None
        tier = None
        if cev is not None and aev is not None and upper is not None:
            if val <= upper:
                score, tier = 100, 'within_twqr'
            elif val <= cev:
                score, tier = 60, 'twqr_to_cev'
            elif val <= aev:
                score, tier = 25, 'cev_to_aev'
            else:
                score, tier = 0, 'beyond_aev'
        elif compliant is True:
            score, tier = 100, 'compliant'
        elif compliant is False:
            score, tier = 0, 'violation'
        else:
            continue

        breakdown.append({
            'indicator_code': m.get('indicator_code'),
            'indicator_name': m.get('indicator_name'),
            'measured_val':   val,
            'tier':           tier,
            'score':          score,
        })
        total += score
        n += 1

    if n == 0:
        return {'overall_score': None, 'grade': 'Insufficient data', 'breakdown': [], 'n_variables': 0, 'achieves_target': False}

    overall = round(total / n, 1)
    if overall >= 90:
        grade = 'Excellent'
    elif overall >= 75:
        grade = 'Good'
    elif overall >= 50:
        grade = 'Fair'
    elif overall >= 25:
        grade = 'Poor'
    else:
        grade = 'Critical'

    return {
        'overall_score': overall,
        'grade':         grade,
        'breakdown':     breakdown,
        'n_variables':   n,
        'achieves_target': overall >= 90,
    }
