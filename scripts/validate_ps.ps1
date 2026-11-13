#=====================================================================
# validate_ps.ps1
#   - Streams the REES46 October-2019 CSV with .NET TextFieldParser
#   - Handles quoted fields correctly (no manual split)
#   - Counts malformed rows (wrong column count) separately
#   - Shows progress every 1 000 000 rows
#   - Writes the two markdown reports only after the whole file has been
#     processed successfully
#   - Works on Windows PowerShell 5.1 and later
#=====================================================================

# --------------------------- 1. Paths --------------------------------
$csvPath        = 'D:\AbandoScope_Analytics\data\raw\2019-Oct.csv'
$reportPathTmp  = 'D:\AbandoScope_Analytics\docs\validation_report.tmp.md'
$reportPath     = 'D:\AbandoScope_Analytics\docs\validation_report.md'
$dictPathTmp    = 'D:\AbandoScope_Analytics\docs\data_dictionary.tmp.md'
$dictPath       = 'D:\AbandoScope_Analytics\docs\data_dictionary.md'

# --------------------------- 2. Expected columns -----------------------
$expected = @(
    'event_time','event_type','product_id','category_id','category_code',
    'brand','price','user_id','user_session'
)

# --------------------------- 3. Counters -----------------------------
$totalRows      = 0
$malformedRows  = 0
$eventCounts    = @{}
$missingCounts  = @{}
$minTime        = ''
$maxTime        = ''
$header         = $null

# Helper: increment a hashtable counter
function Increment-Counter {
    param(
        [hashtable]$Table,
        [string]$Key
    )
    if (-not $Table.ContainsKey($Key)) { $Table[$Key] = 0 }
    $Table[$Key] += 1
}

# --------------------------- 4. Stream CSV ---------------------------
# TextFieldParser is in the Microsoft.VisualBasic assembly
Add-Type -AssemblyName Microsoft.VisualBasic

$parser = New-Object Microsoft.VisualBasic.FileIO.TextFieldParser $csvPath
$parser.TextFieldType = [Microsoft.VisualBasic.FileIO.FieldType]::Delimited
$parser.SetDelimiters(',')                 # comma separator
$parser.HasFieldsEnclosedInQuotes = $true   # quoted-field support
$parser.TrimWhiteSpace = $true

try {
    # ----- Header ----------------------------------------------------
    if ($parser.EndOfData) {
        throw "CSV file is empty - no header row found."
    }
    $header = $parser.ReadFields()
    # Initialise missing-value counters for each column
    foreach ($col in $header) { $missingCounts[$col] = 0 }

    # Verify header - exact order and count must match $expected
    $headerMatches = $true
    if ($header.Count -ne $expected.Count) { $headerMatches = $false }
    else {
        for ($i = 0; $i -lt $expected.Count; $i++) {
            if ($header[$i] -ne $expected[$i]) { $headerMatches = $false; break }
        }
    }
    if (-not $headerMatches) {
        throw ("Header does not match expected columns.`n" +
               "Expected: $($expected -join ', ')`n" +
               "Found   : $($header -join ', ')"
        )
    }

    # Indexes of the columns we need (using static Array.IndexOf)
    $idxEventType = [Array]::IndexOf($header, 'event_type')
    $idxEventTime = [Array]::IndexOf($header, 'event_time')
    if ($idxEventType -lt 0 -or $idxEventTime -lt 0) {
        throw "Required columns 'event_type' or 'event_time' missing in header."
    }

    # ----- Data rows -------------------------------------------------
    while (-not $parser.EndOfData) {
        $fields = $parser.ReadFields()
        $totalRows++

        # ----- Malformed-row handling ---------------------------------
        if ($fields.Count -ne $header.Count) {
            $malformedRows++
            continue   # skip this row - do NOT pad or truncate
        }

        # ----- Missing-value accounting --------------------------------
        for ($i = 0; $i -lt $header.Count; $i++) {
            if ([string]::IsNullOrEmpty($fields[$i])) {
                $missingCounts[$header[$i]]++
            }
        }

        # ----- Event-type counting ------------------------------------
        $ev = $fields[$idxEventType]
        Increment-Counter -Table $eventCounts -Key $ev

        # ----- Min / Max timestamp ------------------------------------
        $tStr = $fields[$idxEventTime]
        if (-not [string]::IsNullOrEmpty($tStr)) {
            if ($minTime -eq '' -or $tStr -lt $minTime) { $minTime = $tStr }
            if ($maxTime -eq '' -or $tStr -gt $maxTime) { $maxTime = $tStr }
        }

        # ----- Progress output -----------------------------------------
        if ($totalRows % 1000000 -eq 0) {
            Write-Host ("Processed {0:N0} rows ..." -f $totalRows) -ForegroundColor Cyan
        }
    }

    # ------------------- 5. Build reports (temp files) ---------------
    # Ensure output directories exist
    New-Item -ItemType Directory -Path (Split-Path $reportPathTmp) -Force | Out-Null
    New-Item -ItemType Directory -Path (Split-Path $dictPathTmp)   -Force | Out-Null

    # ----- Validation report -----------------------------------------
    $report = New-Object System.Text.StringBuilder
    $report.AppendLine('# Validation Report for 2019-Oct.csv') | Out-Null
    $report.AppendLine() | Out-Null
    $report.AppendLine('## Header verification') | Out-Null
    $report.AppendLine("Expected columns ($($expected.Count)): $($expected -join ', ')" ) | Out-Null
    $report.AppendLine("Actual columns   ($($header.Count)): $($header -join ', ')" ) | Out-Null
    $report.AppendLine('Header matches expected order: Yes') | Out-Null
    $report.AppendLine() | Out-Null

    $report.AppendLine('## Row counts') | Out-Null
    $report.AppendLine("Total data rows (excluding header): $totalRows") | Out-Null
    $report.AppendLine("Malformed rows (wrong column count): $malformedRows") | Out-Null
    $report.AppendLine() | Out-Null

    $report.AppendLine('## Event type distribution') | Out-Null
    $eventCounts.GetEnumerator() |
        Sort-Object -Property Value -Descending |
        ForEach-Object { $report.AppendLine("- $($_.Name): $($_.Value)") | Out-Null }
    $report.AppendLine() | Out-Null

    $report.AppendLine('## Missing values per column') | Out-Null
    $validRows = $totalRows - $malformedRows
    foreach ($col in $header) {
        $miss = $missingCounts[$col]
        if ($validRows -gt 0) {
            $pct = $miss / $validRows * 100
        }
        else {
            $pct = 0
        }
        $report.AppendLine(("- {0}: {1} missing ({2:F4}%) (out of {3} valid rows)" -f $col, $miss, $pct, $validRows)) | Out-Null
    }
    $report.AppendLine() | Out-Null

    $report.AppendLine('## Event time range') | Out-Null
    if ($minTime -is [datetime]) {
        $report.AppendLine("- Minimum event_time: $($minTime.ToString('o'))") | Out-Null
        $report.AppendLine("- Maximum event_time: $($maxTime.ToString('o'))") | Out-Null
    }
    else {
        $report.AppendLine("- Minimum event_time (raw string): $minTime") | Out-Null
        $report.AppendLine("- Maximum event_time (raw string): $maxTime") | Out-Null
    }
    $report.AppendLine() | Out-Null

    $report.AppendLine('## Duplicate record check') | Out-Null
    $report.AppendLine('Full-file duplicate detection was not performed because storing a hash for each of the ~150 M rows would exceed typical memory limits on this workstation.') | Out-Null
    $report.AppendLine('If required, duplicates can be identified with external tools that operate on sorted data or by using a disk-based hash set in multiple passes.') | Out-Null

    # Write temporary report atomically
    [System.IO.File]::WriteAllText($reportPathTmp, $report.ToString(), [System.Text.Encoding]::UTF8)

    # ----- Data dictionary -------------------------------------------
    $dict = @"
# Data Dictionary - 2019-Oct.csv

The following columns are present in the CSV (as observed from the header).

"@

    $descriptions = @{
        event_time   = 'Timestamp of the event (UTC).'
        event_type   = 'Interaction type - one of view, cart, remove_from_cart, purchase.'
        product_id   = 'Unique identifier of the product (integer).'
        category_id  = 'Numeric identifier of the product category.'
        category_code= 'Hierarchical category code (e.g., "electronics.smartphone"); may contain nulls.'
        brand        = 'Brand name of the product; nullable.'
        price        = 'Price of the product at the time of the event (float).'
        user_id      = 'Anonymous unique identifier for the customer (integer).'
        user_session = 'UUID representing a browsing session; resets when the user leaves the site.'
    }
    foreach ($col in $header) {
        if ($descriptions.ContainsKey($col)) {
            $desc = $descriptions[$col]
        }
        else {
            $desc = 'No description available.'
        }
        $dict += "- **$col**: $desc`n"
    }
    $dict += "`nAll values are stored as plain-text strings in the CSV; numeric columns can be cast to int/float during analysis.`n"

    [System.IO.File]::WriteAllText($dictPathTmp, $dict, [System.Text.Encoding]::UTF8)

    # ------------------- 6. Commit reports ---------------------------
    Move-Item -Force -Path $reportPathTmp -Destination $reportPath
    Move-Item -Force -Path $dictPathTmp   -Destination $dictPath

    Write-Host "`nValidation completed successfully." -ForegroundColor Green
    Write-Host "Reports written to:" -ForegroundColor Green
    Write-Host " - $reportPath"
    Write-Host " - $dictPath"
}
catch {
    # ------- Any error aborts the process; temp files are removed ----------
    Write-Error "Validation failed: $_"
    if (Test-Path $reportPathTmp) { Remove-Item $reportPathTmp -Force }
    if (Test-Path $dictPathTmp)   { Remove-Item $dictPathTmp   -Force }
    throw   # re-throw to keep the exit code non-zero
}
finally {
    # Ensure the parser is always closed even on error
    if ($parser) { $parser.Close() }
}
