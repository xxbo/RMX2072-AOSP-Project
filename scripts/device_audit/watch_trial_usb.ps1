param(
    [Parameter(Mandatory)][string] $Output,
    [Parameter(Mandatory)][string] $HandoffEvents,
    [int] $TimeoutSeconds = 600
)
$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath $Output) { throw "USB capture already exists" }
$edl = @(Get-PnpDevice -PresentOnly | Where-Object InstanceId -Like 'USB\VID_05C6&PID_9008*')
if ($edl.Count -ne 1) { throw 'Expected one RMX2072 EDL device before the trial reset' }
function Location($Device) {
    (Get-PnpDeviceProperty -InstanceId $Device.InstanceId -KeyName DEVPKEY_Device_LocationPaths).Data |
        Where-Object { $_ -like 'PCIROOT*' } | Select-Object -First 1
}
$port = Location $edl[0]
if (!$port) { throw 'No physical USB port identity' }
$deadline = [DateTimeOffset]::UtcNow.AddSeconds($TimeoutSeconds)
while ([DateTimeOffset]::UtcNow -lt $deadline) {
    $usb = @(Get-PnpDevice -PresentOnly -InstanceId 'USB\VID_*')
    $properties = Get-PnpDeviceProperty -InstanceId $usb.InstanceId -ErrorAction SilentlyContinue -KeyName DEVPKEY_Device_LocationPaths,DEVPKEY_Device_CompatibleIds
    $byDevice = $properties | Group-Object InstanceId -AsHashTable -AsString
    $devices = foreach ($device in $usb) {
        $rows = $byDevice[$device.InstanceId]
        $path = ($rows | Where-Object KeyName -eq DEVPKEY_Device_LocationPaths).Data |
            Where-Object { $_ -like 'PCIROOT*' } | Select-Object -First 1
        if ($path -eq $port -or ($path -and $path.StartsWith("$port#USBMI("))) {
            $ids = ($rows | Where-Object KeyName -eq DEVPKEY_Device_CompatibleIds).Data
            [pscustomobject]@{ id = $device.InstanceId.Split('\')[1]; class = $device.Class; compatible = @($ids) }
        }
    }
    $row = [ordered]@{ utc = [DateTimeOffset]::UtcNow.ToString('o'); devices = @($devices | Where-Object { $_ }) }
    Add-Content -LiteralPath $Output -Value ($row | ConvertTo-Json -Depth 4 -Compress) -Encoding utf8
    if ((Test-Path -LiteralPath $HandoffEvents) -and
        (Select-String -Path $HandoffEvents -SimpleMatch 'recovery_boot' -Quiet)) { break }
    Start-Sleep -Milliseconds 800
}
