

def calculate_sustainability_index(reliability, resilience, vulnerability,
                                   w_r=1, w_s=1, w_v=1):
    """
    Calculates Integrated Sustainability Index (ISI).

    ISI = (w_r*R + w_s*S + w_v*(1 - V)) / (w_r + w_s + w_v)

    Parameters:
        reliability, resilience, vulnerability (float)
        w_r, w_s, w_v (float): Optional weighting factors.

    Returns:
        float: ISI score (0–1 scale)
    """
    try:
        reliability /= 100
        resilience /= 100
        normalized_vul = vulnerability / max(vulnerability, 1)

        isi = (w_r * reliability + w_s * resilience + w_v * (1 - normalized_vul)) / (w_r + w_s + w_v)
        return round(isi, 3)
    except Exception:
        return 0.0

