# Run in an elevated PowerShell after opening JARVIS on this PC.
# Allows only TCP 9443 on this PC's private Ethernet interface, for the running
# JARVIS executable. Does not publish port 8000, disable the firewall or touch NAT.
$ErrorActionPreference = 'Stop'
$principal = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Abra o PowerShell como administrador para criar esta regra específica.'
}
$listener = Get-NetTCPConnection -LocalPort 8000 -State Listen | Select-Object -First 1
if (-not $listener) { throw 'Abra o JARVIS antes de executar este script.' }
$program = (Get-Process -Id $listener.OwningProcess).Path
if (-not $program -or -not (Test-Path -LiteralPath $program)) { throw 'Não foi possível identificar o executável do JARVIS.' }
$interface = Get-NetIPAddress -AddressFamily IPv4 -IPAddress '192.168.15.13'
if (-not $interface) { throw 'O endereço local do PC mudou. Atualize a configuração antes de criar a regra.' }
$profile = Get-NetConnectionProfile -InterfaceIndex $interface.InterfaceIndex
if ($profile.NetworkCategory -ne 'Private') { throw 'Esta regra foi preparada para sua rede doméstica Privada. Confira a classificação da rede antes de continuar.' }
$name = 'Jarvis-Direct-TLS-9443'
if (Get-NetFirewallRule -Name $name -ErrorAction SilentlyContinue) {
    Write-Output 'A regra já existe. Confira seus filtros no Firewall do Windows; nenhuma regra foi alterada.'
    return
}
New-NetFirewallRule -Name $name -DisplayName 'JARVIS — canal direto TLS 9443' -Group 'Jarvis Direct' `
    -Direction Inbound -Action Allow -Enabled True -Protocol TCP -LocalPort 9443 `
    -LocalAddress '192.168.15.13' -InterfaceAlias $interface.InterfaceAlias -Profile Private -Program $program | Out-Null
Write-Output 'Regra específica criada para o executável atual do JARVIS, TCP 9443. O roteador não foi alterado.'
# To undo only this rule: Remove-NetFirewallRule -Name 'Jarvis-Direct-TLS-9443'
