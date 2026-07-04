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
    def _to_meq(code, mg_L):
        eq = ION_EQ_WEIGHTS.get(code)
        if eq is None or mg_L is None:
            return 0.0
        return max(0.0, float(mg_L)) / eq

    ca_meq   = _to_meq('CA',   concentrations_mg_L.get('CA',   0))
    mg_meq   = _to_meq('MG',   concentrations_mg_L.get('MG',   0))
    na_meq   = _to_meq('NA',   concentrations_mg_L.get('NA',   0))
    k_meq    = _to_meq('K',    concentrations_mg_L.get('K',    0))
    hco3_meq = _to_meq('HCO3', concentrations_mg_L.get('HCO3', 0))
    co3_meq  = _to_meq('CO3',  concentrations_mg_L.get('CO3',  0))
    cl_meq   = _to_meq('CL',   concentrations_mg_L.get('CL',   0))
    so4_meq  = _to_meq('SO4',  concentrations_mg_L.get('SO4',  0))

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
    def _to_meq(code, mg_L):
        eq = ION_EQ_WEIGHTS.get(code)
        if eq is None or mg_L is None:
            return 0.0
        return max(0.0, float(mg_L)) / eq

    arms = [
        {
            'cation':  'Na+K',
            'anion':   'Cl',
            'cat_meq': round(_to_meq('NA', concentrations_mg_L.get('NA', 0))
                           + _to_meq('K',  concentrations_mg_L.get('K', 0)), 3),
            'an_meq':  round(_to_meq('CL', concentrations_mg_L.get('CL', 0)), 3),
        },
        {
            'cation':  'Ca',
            'anion':   'SO4',
            'cat_meq': round(_to_meq('CA',  concentrations_mg_L.get('CA', 0)), 3),
            'an_meq':  round(_to_meq('SO4', concentrations_mg_L.get('SO4', 0)), 3),
        },
        {
            'cation':  'Mg',
            'anion':   'HCO3+CO3',
            'cat_meq': round(_to_meq('MG',  concentrations_mg_L.get('MG', 0)), 3),
            'an_meq':  round(_to_meq('HCO3', concentrations_mg_L.get('HCO3', 0))
                           + _to_meq('CO3',  concentrations_mg_L.get('CO3', 0)), 3),
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
