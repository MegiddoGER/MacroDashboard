<#
.SYNOPSIS
    Richtet MacroDashboard als Autostart-Aufgabe ein, damit die LIVE-Uhr laeuft.

.DESCRIPTION
    Die Fundamental- und Sentiment-Haelfte der Analyse (elf Indikatoren) ist
    historisch NICHT nachpruefbar: der Backfill ruft calc_technical_score(),
    weil _score_fundamental und _score_sentiment ihre Daten aus der Gegenwart
    beziehen und ein Replay damit Look-Ahead waere. Diese Haelfte ist
    ausschliesslich vorwaerts messbar, ueber LIVE-Snapshots.

    Daraus folgt die Eigenschaft, um die es hier geht: **ein Tag, an dem die
    Anwendung nicht lief, ist unwiederbringlich.** Es gibt kein Nachtragen.
    Am 2026-09-09 stand die Uhr fuenf Tage still (juengster LIVE-Snapshot vom
    04.09.), schlicht weil kein Prozess lief. Genau das verhindert diese
    Aufgabe.

    Der taegliche Gating-Lauf feuert um SNAPSHOT_RUN_TIME (Vorgabe 18:30 CET,
    siehe config.py) aus dem lifespan-Handler von main.py. Er braucht also
    keinen Server-Anfrageverkehr, aber einen LAUFENDEN Prozess zu dieser
    Uhrzeit.

.NOTES
    Warum eine Anmelde-Aufgabe und nicht ein Dienst:
    launcher.py zeigt ein Tray-Symbol (pystray) und braucht dafuer eine
    interaktive Desktop-Sitzung. Ein Dienst ("run whether user is logged on
    or not") laeuft in Sitzung 0 ohne Desktop — das Tray-Symbol erschiene nie
    und die Anwendung waere nicht bedienbar. Wer die Uhr auch ohne Anmeldung
    braucht, muss stattdessen uvicorn ohne launcher.py als Dienst fuehren;
    das ist eine andere Einrichtung und hier bewusst nicht gebaut.

.EXAMPLE
    .\autostart_einrichten.ps1
    Richtet die Aufgabe ein (idempotent, ueberschreibt eine vorhandene).

.EXAMPLE
    .\autostart_einrichten.ps1 -Jetzt
    Richtet sie ein und startet die Anwendung sofort mit.

.EXAMPLE
    .\autostart_einrichten.ps1 -Status
    Zeigt nur an, ob die Aufgabe existiert und wann sie zuletzt lief.

.EXAMPLE
    .\autostart_einrichten.ps1 -Entfernen
    Loescht die Aufgabe wieder. Ein laufender Prozess bleibt unberuehrt.
#>

[CmdletBinding(DefaultParameterSetName = "Einrichten")]
param(
    [Parameter(ParameterSetName = "Einrichten")]
    [switch]$Jetzt,

    [Parameter(ParameterSetName = "Status")]
    [switch]$Status,

    [Parameter(ParameterSetName = "Entfernen")]
    [switch]$Entfernen,

    # Verzoegerung nach der Anmeldung. Nicht null: beim Anmelden konkurriert
    # der Start mit allem anderen, was Windows gerade hochfaehrt, und
    # yfinance-Abrufe brauchen ein Netz, das schon steht.
    [Parameter(ParameterSetName = "Einrichten")]
    [string]$Verzoegerung = "PT2M"
)

$ErrorActionPreference = "Stop"

$AufgabenName = "MacroDashboard"
$Projekt      = Split-Path -Parent $MyInvocation.MyCommand.Path
$Launcher     = Join-Path $Projekt "launcher.py"

function Schreib($text, $farbe = "Gray") { Write-Host $text -ForegroundColor $farbe }

# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

if ($Status) {
    $t = Get-ScheduledTask -TaskName $AufgabenName -ErrorAction SilentlyContinue
    if (-not $t) {
        Schreib "Aufgabe '$AufgabenName' ist NICHT eingerichtet." "Yellow"
        Schreib "  Einrichten mit: .\autostart_einrichten.ps1"
        exit 1
    }
    $info = Get-ScheduledTaskInfo -TaskName $AufgabenName
    Schreib "Aufgabe '$AufgabenName': $($t.State)" "Green"
    Schreib "  Letzter Lauf   : $($info.LastRunTime)  (Ergebnis $($info.LastTaskResult))"
    Schreib "  Naechster Lauf : $($info.NextRunTime)"

    $port = (Select-String -Path (Join-Path $Projekt "config.py") -Pattern 'APP_PORT.*?(\d+)' |
             Select-Object -First 1).Matches.Groups[1].Value
    if (-not $port) { $port = "8501" }
    $lauft = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($lauft) {
        Schreib "  Anwendung      : laeuft auf Port $port (PID $($lauft[0].OwningProcess))" "Green"
    } else {
        Schreib "  Anwendung      : laeuft derzeit NICHT (Port $port frei)" "Yellow"
    }
    exit 0
}

# ---------------------------------------------------------------------------
# Entfernen
# ---------------------------------------------------------------------------

if ($Entfernen) {
    if (Get-ScheduledTask -TaskName $AufgabenName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $AufgabenName -Confirm:$false
        Schreib "Aufgabe '$AufgabenName' entfernt." "Green"
        Schreib "Ein bereits laufender Prozess bleibt davon unberuehrt."
    } else {
        Schreib "Aufgabe '$AufgabenName' existiert nicht — nichts zu tun." "Yellow"
    }
    exit 0
}

# ---------------------------------------------------------------------------
# Einrichten
# ---------------------------------------------------------------------------

if (-not (Test-Path $Launcher)) {
    throw "launcher.py nicht gefunden unter '$Launcher'. Das Skript muss im Projektstamm liegen."
}

# pyw.exe statt py.exe: launcher.py ist eine Tray-Anwendung. Mit py.exe haengt
# ihr bei jeder Anmeldung ein Konsolenfenster an, das der Benutzer wegklicken
# muesste — und ein versehentliches Schliessen beendet die Uhr.
$Pyw = (Get-Command pyw.exe -ErrorAction SilentlyContinue).Source
if (-not $Pyw) {
    $Pyw = (Get-Command py.exe -ErrorAction SilentlyContinue).Source
    if (-not $Pyw) { throw "Weder pyw.exe noch py.exe gefunden. Ist der Python-Launcher installiert?" }
    Schreib "pyw.exe nicht gefunden — verwende py.exe (mit Konsolenfenster)." "Yellow"
}

$Aktion = New-ScheduledTaskAction -Execute $Pyw -Argument "`"$Launcher`"" -WorkingDirectory $Projekt

$Ausloeser = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$Ausloeser.Delay = $Verzoegerung

# LogonType Interactive ist die Bedingung fuer das Tray-Symbol (siehe .NOTES).
$Konto = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
                                    -LogonType Interactive -RunLevel Limited

$Einstellungen = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 5) `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

# ExecutionTimeLimit Zero = kein Zeitlimit. Die Vorgabe von drei Tagen wuerde
# den Prozess sonst irgendwann beenden, und die Uhr staende wieder still,
# ohne dass es jemandem auffiele.
# DontStopIfGoingOnBatteries: ein Notebook im Akkubetrieb um 18:30 soll den
# Snapshot trotzdem aufzeichnen — der Tag ist sonst verloren.

Register-ScheduledTask -TaskName $AufgabenName `
    -Action $Aktion -Trigger $Ausloeser -Principal $Konto -Settings $Einstellungen `
    -Description "Startet MacroDashboard bei der Anmeldung, damit der taegliche LIVE-Snapshot (SNAPSHOT_RUN_TIME, Vorgabe 18:30 CET) aufgezeichnet wird. Ein nicht aufgezeichneter Tag laesst sich nicht nachtragen." `
    -Force | Out-Null

Schreib "Aufgabe '$AufgabenName' eingerichtet." "Green"
Schreib "  Programm     : $Pyw"
Schreib "  Argument     : $Launcher"
Schreib "  Arbeitsordner: $Projekt"
Schreib "  Ausloeser    : bei Anmeldung von $env:USERDOMAIN\$env:USERNAME, Verzoegerung $Verzoegerung"
Schreib ""
Schreib "Die Uhr laeuft ab der naechsten Anmeldung von selbst."
Schreib "Pruefen mit : .\autostart_einrichten.ps1 -Status"
Schreib "Entfernen   : .\autostart_einrichten.ps1 -Entfernen"

if ($Jetzt) {
    $port = "8501"
    $lauft = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($lauft) {
        Schreib ""
        Schreib "Port $port ist bereits belegt (PID $($lauft[0].OwningProcess)) — nicht erneut gestartet." "Yellow"
    } else {
        Start-ScheduledTask -TaskName $AufgabenName
        Schreib ""
        Schreib "Anwendung gestartet." "Green"
    }
}
