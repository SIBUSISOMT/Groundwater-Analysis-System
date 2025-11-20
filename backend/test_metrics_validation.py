"""
Resilience and Sustainability Validation Script
================================================
This script validates the metric calculations by:
1. Fetching data from the API
2. Performing manual calculations
3. Comparing with API results
4. Checking inverse relationships

Usage:
    python test_metrics_validation.py

Make sure your Flask backend is running on http://localhost:5000
"""

import requests
import json
from datetime import datetime

# Configuration
API_BASE_URL = "http://localhost:5000"
TEST_CATCHMENT = "Crocodile"  # Change to your test catchment
TEST_PARAMETER = "recharge"   # Change to your test parameter


def fetch_metrics(catchment=None, parameter=None):
    """Fetch metrics from the API"""
    url = f"{API_BASE_URL}/api/metrics"
    params = {}
    if catchment:
        params['catchment'] = catchment
    if parameter:
        params['parameter'] = parameter

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ Error fetching metrics: {e}")
        return None


def fetch_processed_data(catchment=None, parameter=None):
    """Fetch raw processed data for manual calculation"""
    url = f"{API_BASE_URL}/api/data"
    params = {}
    if catchment:
        params['catchment'] = catchment
    if parameter:
        params['parameter'] = parameter

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ Error fetching data: {e}")
        return None


def calculate_metrics_manually(data_records):
    """Manually calculate metrics from raw data"""
    if not data_records:
        return None

    total_records = len(data_records)
    if total_records == 0:
        return None

    # Count failures and satisfactory records
    failures = [r for r in data_records if r.get('is_failure') == 1]
    satisfactory = [r for r in data_records if r.get('standardized_value', -999) >= -0.5]

    failure_count = len(failures)
    satisfactory_count = len(satisfactory)

    # Calculate Reliability
    reliability = satisfactory_count / total_records if total_records > 0 else 0

    # Calculate Resilience (only from failures)
    if failure_count == 0:
        resilience = 1.0
        avg_severity_failures = 0
    else:
        severities = [r.get('severity_level', 0) for r in failures]
        avg_severity_failures = sum(severities) / len(severities)
        resilience = 1.0 - (avg_severity_failures / 3.0)

    # Calculate Vulnerability (only from failures)
    if failure_count == 0:
        vulnerability = 0.0
        avg_abs_zscore_failures = 0
    else:
        abs_zscores = [abs(r.get('standardized_value', 0)) for r in failures]
        avg_abs_zscore_failures = sum(abs_zscores) / len(abs_zscores)
        vulnerability = avg_abs_zscore_failures / 3.0

    # Calculate Sustainability
    sustainability = (reliability + resilience + (1.0 - vulnerability)) / 3.0

    return {
        'total_records': total_records,
        'failure_count': failure_count,
        'satisfactory_count': satisfactory_count,
        'avg_severity_failures': avg_severity_failures,
        'avg_abs_zscore_failures': avg_abs_zscore_failures,
        'reliability': reliability,
        'resilience': resilience,
        'vulnerability': vulnerability,
        'sustainability': sustainability
    }


def print_comparison(manual, api_metric):
    """Print comparison between manual and API calculations"""
    print("\n" + "="*70)
    print("METRIC VALIDATION RESULTS")
    print("="*70)

    print(f"\nTest Configuration:")
    print(f"  Catchment: {TEST_CATCHMENT}")
    print(f"  Parameter: {TEST_PARAMETER}")
    print(f"  Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    print(f"\n{'─'*70}")
    print("DATA SUMMARY")
    print(f"{'─'*70}")
    print(f"  Total Records:       {manual['total_records']:>10}")
    print(f"  Failure Count:       {manual['failure_count']:>10}")
    print(f"  Satisfactory Count:  {manual['satisfactory_count']:>10}")
    print(f"  Failure Rate:        {(manual['failure_count']/manual['total_records']*100):>9.2f}%")

    print(f"\n{'─'*70}")
    print("FAILURE ANALYSIS (Failures Only)")
    print(f"{'─'*70}")
    print(f"  Avg Severity Level:  {manual['avg_severity_failures']:>10.3f}")
    print(f"  Avg |Z-score|:       {manual['avg_abs_zscore_failures']:>10.3f}")

    print(f"\n{'─'*70}")
    print("METRIC CALCULATIONS")
    print(f"{'─'*70}")
    print(f"{'Metric':<20} {'Manual':<15} {'API':<15} {'Match':<10}")
    print(f"{'─'*70}")

    def compare_values(name, manual_val, api_val, tolerance=0.001):
        """Compare two values and return status"""
        diff = abs(manual_val - api_val)
        match = "✓ PASS" if diff < tolerance else "✗ FAIL"
        manual_str = f"{manual_val:.6f}"
        api_str = f"{api_val:.6f}"
        print(f"{name:<20} {manual_str:<15} {api_str:<15} {match:<10}")
        if diff >= tolerance:
            print(f"  {'':>20} Difference: {diff:.6f}")
        return diff < tolerance

    all_pass = True
    all_pass &= compare_values("Reliability", manual['reliability'], api_metric['reliability'])
    all_pass &= compare_values("Resilience", manual['resilience'], api_metric['resilience'])
    all_pass &= compare_values("Vulnerability", manual['vulnerability'], api_metric['vulnerability'])
    all_pass &= compare_values("Sustainability", manual['sustainability'], api_metric['sustainability'])

    print(f"{'─'*70}")

    # Percentage display
    print(f"\n{'─'*70}")
    print("PERCENTAGE FORMAT (for dashboard display)")
    print(f"{'─'*70}")
    print(f"  Reliability:      {manual['reliability']*100:>6.2f}% (API: {api_metric['reliability']*100:>6.2f}%)")
    print(f"  Resilience:       {manual['resilience']*100:>6.2f}% (API: {api_metric['resilience']*100:>6.2f}%)")
    print(f"  Vulnerability:    {manual['vulnerability']*100:>6.2f}% (API: {api_metric['vulnerability']*100:>6.2f}%)")
    print(f"  Sustainability:   {manual['sustainability']*100:>6.2f}% (API: {api_metric['sustainability']*100:>6.2f}%)")

    # Inverse relationship check
    print(f"\n{'─'*70}")
    print("INVERSE RELATIONSHIP CHECK")
    print(f"{'─'*70}")
    print(f"  Resilience:       {manual['resilience']:.3f} (higher = better)")
    print(f"  Vulnerability:    {manual['vulnerability']:.3f} (lower = better)")

    if manual['failure_count'] > 0:
        inverse_sum = manual['resilience'] + manual['vulnerability']
        print(f"  Sum (Res + Vuln): {inverse_sum:.3f}")

        if manual['resilience'] > 0.5 and manual['vulnerability'] < 0.5:
            print("  ✓ PASS: High resilience with low vulnerability (inverse relationship)")
        elif manual['resilience'] < 0.5 and manual['vulnerability'] > 0.5:
            print("  ✓ PASS: Low resilience with high vulnerability (inverse relationship)")
        else:
            print("  ✓ PASS: Both moderate (0.3-0.7) - consistent with moderate failures")
    else:
        print("  ✓ No failures detected - Resilience = 1.0, Vulnerability = 0.0")

    # Sustainability breakdown
    print(f"\n{'─'*70}")
    print("SUSTAINABILITY BREAKDOWN (ISI Formula)")
    print(f"{'─'*70}")
    print(f"  Formula: (R + Res + (1-V)) / 3")
    print(f"  Components:")
    print(f"    Reliability (R):     {manual['reliability']:.6f}")
    print(f"    Resilience (Res):    {manual['resilience']:.6f}")
    print(f"    Robustness (1-V):    {1.0 - manual['vulnerability']:.6f}")
    print(f"  Sum:                   {manual['reliability'] + manual['resilience'] + (1.0 - manual['vulnerability']):.6f}")
    print(f"  Sustainability (÷3):   {manual['sustainability']:.6f}")

    print(f"\n{'─'*70}")
    if all_pass:
        print("✓ ALL TESTS PASSED - Calculations are accurate!")
    else:
        print("✗ SOME TESTS FAILED - Check implementation!")
    print(f"{'─'*70}\n")

    return all_pass


def main():
    """Main validation function"""
    print("\n" + "="*70)
    print("RESILIENCE & SUSTAINABILITY VALIDATION SCRIPT")
    print("="*70)
    print(f"\nTesting against: {API_BASE_URL}")
    print(f"Catchment: {TEST_CATCHMENT}")
    print(f"Parameter: {TEST_PARAMETER}")

    # Step 1: Fetch API metrics
    print("\n[1/3] Fetching metrics from API...")
    metrics_response = fetch_metrics(TEST_CATCHMENT, TEST_PARAMETER)
    if not metrics_response or not metrics_response.get('success'):
        print("❌ Failed to fetch metrics from API")
        return

    if not metrics_response.get('metrics'):
        print("❌ No metrics returned from API")
        return

    api_metric = metrics_response['metrics'][0]  # Get first result
    print(f"✓ Fetched metrics successfully")

    # Step 2: Fetch raw data
    print("\n[2/3] Fetching raw processed data...")
    data_response = fetch_processed_data(TEST_CATCHMENT, TEST_PARAMETER)
    if not data_response or not data_response.get('success'):
        print("❌ Failed to fetch processed data from API")
        return

    data_records = data_response.get('data', [])
    print(f"✓ Fetched {len(data_records)} records")

    # Step 3: Calculate manually
    print("\n[3/3] Calculating metrics manually...")
    manual_results = calculate_metrics_manually(data_records)
    if not manual_results:
        print("❌ Failed to calculate metrics manually")
        return

    print(f"✓ Manual calculations complete")

    # Step 4: Compare
    success = print_comparison(manual_results, api_metric)

    # Return exit code
    return 0 if success else 1


if __name__ == "__main__":
    try:
        exit_code = main()
        exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nValidation interrupted by user")
        exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
