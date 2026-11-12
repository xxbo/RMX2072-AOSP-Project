# Reproduce the historical RMX2072 boot-v2 package from the local input cache.
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$WorkDirectory,
    [Parameter(Mandatory)][string]$PriorWorkDirectory,
    [Parameter(Mandatory)][string]$NdkDirectory,
    [Parameter(Mandatory)][string]$OutputDirectory,
    [Parameter(Mandatory)][ValidatePattern('^ufs-host-g3-gsi17-firststage-[a-zA-Z0-9-]+$')][string]$Trial,
    [string]$ProjectVendor,
    [switch]$TraceInitFault
)
$ErrorActionPreference = 'Stop'
$work = (Resolve-Path -LiteralPath $WorkDirectory).Path
$prior = (Resolve-Path -LiteralPath $PriorWorkDirectory).Path
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$out = [IO.Path]::GetFullPath($OutputDirectory)
if ($out -eq $repo -or $out.StartsWith($repo + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Select a private output directory outside the checkout.'
}
if (Test-Path -LiteralPath $out) { throw "Select a new output directory: $out" }
if (($Trial -like '*-firststage-vendor-*') -ne [bool]$ProjectVendor) {
    throw 'Supply the project vendor directory for a vendor trial.'
}
New-Item -Type Directory -Path $out | Out-Null
$prefix = Join-Path $out $Trial
$clang = Join-Path $NdkDirectory 'toolchains/llvm/prebuilt/windows-x86_64/bin/clang.exe'
$dtc = Join-Path $prior 'dtc-ucrt/ucrt64/bin/dtc.exe'
$libfdt = Join-Path $prior 'dtc-ucrt/ucrt64/bin/libfdt-1.dll'
$toolPath = (Join-Path $work 'dtc-runtime/ucrt64/bin') + ';' + (Split-Path $dtc)
$savedPath = $env:PATH
function Run([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program exited with $LASTEXITCODE" }
}
function BootHash([string]$Stage) {
    (Get-Content -LiteralPath "$prefix-$Stage/control.json" -Raw | ConvertFrom-Json).boot_sha256
}
try {
    $env:PATH = "$toolPath;$savedPath"
    Run $clang @('-E','-P','-x','assembler-with-cpp','-nostdinc','-undef','-D__DTS__',
        "-I$work/ufs-headers","$repo/device/realme/bladerunner_48m/dts/rmx2072-ufs-host-g3.dts",'-o',"$prefix.dts")
    Run $dtc @('-@','-I','dts','-O','dtb','-o',"$prefix.dtb","$prefix.dts")
    $overlayHash = (Get-FileHash -LiteralPath "$prefix.dtb").Hash.ToLowerInvariant()
    Run python @("$PSScriptRoot/prepare_legacy_tree_patch.py",'--ufs-host-g3-control',
        '--control-boot',"$work/watchdog-package/boot-diag.img",'--stock-dtbo',"$prior/../outputs/phone-recovery-kit/images/dtbo-stock.img",
        '--libfdt',$libfdt,'--overlay',"$prefix.dtb",'--expected-overlay-sha256',$overlayHash,'--output',"$prefix-base")
    $timer = '360'
    $vendorArgs = @()
    if ($ProjectVendor) {
        $timer = '410'
        $vendorArgs = @('--project-vendor',(Resolve-Path -LiteralPath $ProjectVendor).Path)
    }
    if ($TraceInitFault) { $vendorArgs += '--trace-init-fault' }
    $rd = @("$PSScriptRoot/build_diag_ramdisk.py",'--busybox',"$prior/control-tools/busybox",
        '--reboot-helper',"$prior/control-tools/reboot-edl",'--entry-carrier',"$prior/control-tools/entry-carry",
        '--gadget-bind-delay','20','--return-to-edl-after',$timer,'--trial-id',$Trial,'--ufs-host-g3-test',
        '--super-tools-apks',"$work/super-reference/apks",'--gsi-usb-reader',"$work/gsi-usb-reader",
        '--android-first-stage',"$work/m1-firststage-source/init",'--first-stage-witness',"$work/first-stage-witness")
    Run python ($rd + $vendorArgs + @('--output',"$prefix-rd"))
    Run python @("$PSScriptRoot/prepare_ramdisk_control.py",'--source',"$prefix-base/boot-diag.img",
        '--expected-source-sha256',(BootHash 'base'),'--ramdisk',"$prefix-rd/ramdisk.cpio.gz",'--output',"$prefix-template")
    $kernel = (Get-Content -LiteralPath "$work/ufs-phy-01-package/control.json" -Raw | ConvertFrom-Json).kernel_sha256
    Run python @("$PSScriptRoot/prepare_kernel_control.py",'--source',"$prefix-template/boot-diag.img",
        '--expected-source-sha256',(BootHash 'template'),'--kernel',"$work/ufs-phy-Image",'--expected-kernel-sha256',$kernel,
        '--entry-probe',"$prior/native-entry-probe-cache.bin",'--output',"$prefix-package")
} finally {
    $env:PATH = $savedPath
}
