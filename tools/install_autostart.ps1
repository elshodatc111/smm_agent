# SMM Platforma: kompyuter yoqilganda avtomatik ishga tushish (Task Scheduler).
# Chaqirish: autostart.bat (administrator huquqi bilan). Parametr: install | remove | status
param([string]$Root, [string]$Mode = "install")
$ErrorActionPreference = "Stop"
$TaskName = "SMM Platforma"
$Root = (Resolve-Path $Root).Path.TrimEnd('\')
$Bat = Join-Path $Root "tools\service_run.bat"
$Py = Join-Path $Root ".venv\Scripts\python.exe"
$LogDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Log = Join-Path $LogDir "autostart.log"
function Say($m) { Write-Host $m; Add-Content -Path $Log -Value ("[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $m) }

function Get-Port {
    $port = "8000"
    $envf = Join-Path $Root ".env"
    if (Test-Path $envf) { foreach ($l in Get-Content $envf) { if ($l -match '^\s*PORT\s*=\s*(\d+)') { $port = $Matches[1] } } }
    return $port
}

if ($Mode -eq "remove") {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Say "Avtomatik ishga tushish OCHIRILDI. (Ishlab turgan dastur uchun stop.bat ni bosing.)"
    } else { Say "Avtomatik ishga tushish vazifasi topilmadi (allaqachon o'chirilgan)." }
    exit 0
}

if ($Mode -eq "status") {
    $t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $t) { Say "Avtomatik ishga tushish YOQILMAGAN. autostart.bat ni administrator sifatida ishga tushiring."; exit 0 }
    $i = Get-ScheduledTaskInfo -TaskName $TaskName
    Say ("Vazifa holati: {0}; oxirgi ishga tushish: {1}; oxirgi natija kodi: {2}" -f $t.State, $i.LastRunTime, $i.LastTaskResult)
    try { $r = Invoke-WebRequest -UseBasicParsing -Uri ("http://127.0.0.1:{0}/api/v1/health/" -f (Get-Port)) -TimeoutSec 8; Say "Dastur ishlayapti (javob: $($r.StatusCode))." }
    catch { Say "Dastur hozir javob bermayapti." }
    exit 0
}

if (-not (Test-Path $Py)) {
    Say "XATO: .venv topilmadi. Avval run.bat ni bir marta ishga tushirib, dastur sozlanganini tekshiring, keyin autostart.bat ni qayta ishga tushiring."
    exit 2
}

# SYSTEM hisobida foydalanuvchi PATH (ffmpeg va h.k.) ko'rinmaydi, shuning uchun nusxasini saqlaymiz
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
$machPath = [Environment]::GetEnvironmentVariable("Path", "Machine")
$envBat = Join-Path $Root "tools\service_env.bat"
$line = "set `"PATH=$machPath;$userPath`""
Set-Content -Path $envBat -Value $line -Encoding ASCII

$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument ('/c ""{0}""' -f $Bat) -WorkingDirectory $Root
$tBoot = New-ScheduledTaskTrigger -AtStartup
$tBoot.Delay = "PT45S"
$tLogon = New-ScheduledTaskTrigger -AtLogOn
$tLogon.Delay = "PT30S"
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) { Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false }
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger @($tBoot, $tLogon) -Settings $settings -Principal $principal `
    -Description "SMM Platforma: kompyuter yoqilganda avtomatik ishga tushadi (veb + worker)" | Out-Null
Say "Vazifa yaratildi: kompyuter yoqilgach ~45 soniyada o'zi ishga tushadi (hech kim kirmasa ham)."

# kompyuter uxlab qolmasin (server sifatida ishlaydi)
try {
    powercfg /change standby-timeout-ac 0 | Out-Null
    powercfg /change hibernate-timeout-ac 0 | Out-Null
    powercfg /change monitor-timeout-ac 15 | Out-Null
    Say "Quvvat sozlamasi: tarmoqdan ishlaganda kompyuter uxlamaydi (ekran 15 daqiqada o'chadi)."
} catch { Say "Quvvat sozlamasini o'zgartirib bo'lmadi (kerak bo'lsa qo'lda: Sozlamalar > Quvvat > Uyqu = Hech qachon)." }

# darhol ishga tushiramiz (agar allaqachon ishlayotgan bo'lsa, dastur o'zi ikkinchi nusxani to'xtatadi)
Start-ScheduledTask -TaskName $TaskName
Say "Hozir ishga tushirilmoqda, 40 soniya kuting..."
Start-Sleep -Seconds 40
try {
    $r = Invoke-WebRequest -UseBasicParsing -Uri ("http://127.0.0.1:{0}/api/v1/health/" -f (Get-Port)) -TimeoutSec 10
    Say "TAYYOR: dastur ishlayapti (http://127.0.0.1:$(Get-Port)). Endi kompyuter yoqilganda o'zi ishga tushadi."
} catch {
    Say "Dastur hali javob bermadi. logs\service.log va logs\serve.out.log fayllarini ko'ring. Birinchi ishga tushishda 1-2 daqiqa ketishi mumkin."
}
exit 0
