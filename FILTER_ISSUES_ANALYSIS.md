# Filter Issues Analysis & Fixes

## Problem Identified

Date range filters are **inconsistent** across different pages - sometimes they work, sometimes they don't.

---

## Root Cause Analysis

### **Issue 1: Inconsistent API Parameter Names**

Different pages use different parameter names for date filtering:

| File | Start Date Param | End Date Param | Notes |
|------|-----------------|---------------|-------|
| **script.js** (Main Dashboard) | `start_date` | `end_date` | ✅ Correct |
| **reports.js** (Reports Page) | `start_date` | `end_date` | ✅ Correct |
| **failure-analysis.js** | `start_date` | `end_date` | ✅ Correct |
| **Backend API** `/api/data` | `start_date` | `end_date` | ✅ Expects these names |
| **Backend API** `/api/detailed-records` | `start_date` | `end_date` | ✅ Expects these names |
| **Backend API** `/api/failure-analysis` | ❌ **MISSING** | ❌ **MISSING** | ⚠️ PROBLEM! |

---

### **Issue 2: Backend `/api/failure-analysis` Doesn't Support Date Filters**

**File:** `backend/app.py` lines 1265-1378

**Current Implementation:**
```python
@app.route('/api/failure-analysis', methods=['GET'])
def get_failure_analysis():
    catchment = request.args.get('catchment')
    category = request.args.get('category')
    parameter = request.args.get('parameter')

    # ❌ NO start_date or end_date handling!
```

**What happens:**
1. User selects date range in failure-analysis.js
2. Frontend sends `start_date` and `end_date` parameters
3. Backend **ignores them** completely
4. Returns ALL failure analysis data regardless of date range
5. User thinks "filters aren't working"

---

### **Issue 3: Missing Date Filtering in Aggregation Query**

The failure analysis endpoint aggregates data with `GROUP BY`, but never filters by date range.

**Current Query (lines 1278-1304):**
```sql
SELECT
    c.catchment_name,
    pd.parameter_type,
    COUNT(*) as total_records,
    ...
FROM dbo.ProcessedData pd
INNER JOIN dbo.Catchments c ON pd.catchment_id = c.catchment_id
WHERE 1=1
    -- ✅ Has catchment filter
    -- ✅ Has parameter filter
    -- ❌ NO DATE RANGE FILTERS!
GROUP BY c.catchment_name, pd.parameter_type
```

---

## Impact

### When It Fails:
1. **Failure Analysis page** - Date filters do NOTHING
   - Users select dates → get all data anyway
   - Confusing and unreliable

2. **Reports page** - Works correctly (uses `/api/detailed-records`)
   - Date filters work as expected

3. **Main Dashboard** - Works correctly (uses `/api/data`)
   - Date filters work as expected

---

## Solution

### **Fix 1: Add Date Filter Support to `/api/failure-analysis`**

**Location:** `backend/app.py` line 1265

**Add these lines after line 1302:**

```python
# Add date range filters
if start_date:
    query += " AND CAST(pd.measurement_date AS DATE) >= CAST(? AS DATE)"
    params.append(start_date)

if end_date:
    query += " AND CAST(pd.measurement_date AS DATE) <= CAST(? AS DATE)"
    params.append(end_date)
```

**Full corrected endpoint:**
```python
@app.route('/api/failure-analysis', methods=['GET'])
def get_failure_analysis():
    try:
        catchment = request.args.get('catchment')
        category = request.args.get('category')
        parameter = request.args.get('parameter')
        start_date = request.args.get('start_date')  # ✅ ADD THIS
        end_date = request.args.get('end_date')      # ✅ ADD THIS

        # ... existing query building ...

        # ✅ ADD DATE FILTERS BEFORE GROUP BY
        if start_date:
            query += " AND CAST(pd.measurement_date AS DATE) >= CAST(? AS DATE)"
            params.append(start_date)

        if end_date:
            query += " AND CAST(pd.measurement_date AS DATE) <= CAST(? AS DATE)"
            params.append(end_date)

        query += " GROUP BY c.catchment_name, pd.parameter_type ORDER BY failure_rate DESC"

        # ... rest of the function ...
```

---

### **Fix 2: Add Date Filters to Overall Stats Query Too**

**Location:** `backend/app.py` line 1328

The "overall_stats" query also needs date filtering:

```python
overall_query = """
SELECT
    COUNT(*) as total,
    SUM(CASE WHEN is_failure = 1 THEN 1 ELSE 0 END) as failures,
    COUNT(DISTINCT catchment_id) as catchments
FROM dbo.ProcessedData
WHERE 1=1
"""
overall_params = []

if catchment:
    overall_query += " AND catchment_id = (SELECT catchment_id FROM dbo.Catchments WHERE catchment_name = ?)"
    overall_params.append(catchment)

if param_filter:
    overall_query += " AND LOWER(parameter_type) = ?"
    overall_params.append(param_filter.lower())

# ✅ ADD DATE FILTERS
if start_date:
    overall_query += " AND CAST(measurement_date AS DATE) >= CAST(? AS DATE)"
    overall_params.append(start_date)

if end_date:
    overall_query += " AND CAST(measurement_date AS DATE) <= CAST(? AS DATE)"
    overall_params.append(end_date)
```

---

## Testing Steps

### **1. Test Failure Analysis Page**

**Before Fix:**
```
1. Go to Failure Analysis page
2. Select date range: 2020-01-01 to 2020-12-31
3. Click Apply Filters
4. Result: ❌ Shows ALL data (ignores dates)
```

**After Fix:**
```
1. Go to Failure Analysis page
2. Select date range: 2020-01-01 to 2020-12-31
3. Click Apply Filters
4. Result: ✅ Shows ONLY 2020 data
```

### **2. Test Combined Filters**

```
1. Select Catchment: Crocodile
2. Select Category: Recharge
3. Select Date Range: 2015-01-01 to 2018-12-31
4. Click Apply Filters
5. Expected: Only Crocodile recharge data from 2015-2018
```

### **3. Test Clear Filters**

```
1. Apply filters
2. Click "Clear Filters"
3. Expected: All filter inputs reset, all data shown
```

---

## Expected Behavior After Fix

### ✅ Failure Analysis Page
- Date filters now actually filter data
- Combines with catchment/parameter filters correctly
- Overall stats respect date range

### ✅ All Pages Consistent
- Dashboard: Date filters work ✓
- Reports: Date filters work ✓
- Failure Analysis: Date filters work ✓ (after fix)

### ✅ User Experience
- Predictable filter behavior across all pages
- No confusion about "filters not working"
- Accurate date-filtered failure analysis

---

## Files to Modify

1. **`backend/app.py`**
   - Line ~1265: Add `start_date` and `end_date` parameter extraction
   - Line ~1302: Add date filter conditions to main query
   - Line ~1344: Add date filter conditions to overall stats query

---

## Summary

**Problem:** Date filters on Failure Analysis page were being **ignored by the backend**.

**Cause:** The `/api/failure-analysis` endpoint never implemented date filtering, even though the frontend was sending the parameters.

**Solution:** Add date filter support to the endpoint with proper SQL WHERE clauses.

**Impact:** HIGH - Affects all users trying to analyze failures within specific time periods.

**Difficulty:** LOW - Simple parameter extraction and SQL condition addition.

**Testing:** EASY - Just apply date filters and verify data matches range.
