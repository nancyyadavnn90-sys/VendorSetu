# Opens the generated SRS in Microsoft Word, fills the Table of Contents and page numbers,
# saves it, and exports a PDF copy next to it.
#   powershell -ExecutionPolicy Bypass -File docs\finalize_with_word.ps1
$docx = Join-Path $PSScriptRoot "SRS_VendorSetu.docx"
$pdf  = Join-Path $PSScriptRoot "SRS_VendorSetu.pdf"
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {
    $d = $word.Documents.Open($docx)
    $d.Fields.Update() | Out-Null
    $d.TablesOfContents.Item(1).Update()
    $d.Save()
    $d.SaveAs2($pdf, 17)   # 17 = wdFormatPDF
    "Pages: " + $d.ComputeStatistics(2)
    $d.Close()
} finally {
    $word.Quit()
}
