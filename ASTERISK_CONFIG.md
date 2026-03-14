# SIPinator - Asterisk Konfiguration

## Uebersicht

SIPinator registriert sich als ein einzelner SIP-Endpunkt bei Asterisk.
Wenn ein Anruf fuer eine ueberwachte Extension eingeht, routet Asterisk
den Anruf kurz an SIPinator (loest Push aus), dann an das echte iOS-Geraet.

## pjsip.conf - SIPinator Endpunkt

```ini
; ============================================
; SIPinator Push Notification Bridge
; ============================================

[sipinator-auth]
type=auth
auth_type=userpass
username=sipinator
password=your_secure_password_here

[sipinator-aor]
type=aor
max_contacts=1
remove_existing=yes
qualify_frequency=30
default_expiration=300

[sipinator]
type=endpoint
context=from-internal
disallow=all
allow=ulaw
allow=alaw
auth=sipinator-auth
aors=sipinator-aor
direct_media=no
```

## pjsip.conf - iOS App Endpunkte

Fuer jeden Benutzer, der die iOS App nutzt, einen Endpunkt anlegen:

```ini
; Benutzer 1001
[1001-ios-auth]
type=auth
auth_type=userpass
username=1001-ios
password=secure_password_1001

[1001-ios-aor]
type=aor
max_contacts=1
qualify_frequency=60
default_expiration=120

[1001-ios]
type=endpoint
context=from-internal
disallow=all
allow=opus
allow=ulaw
auth=1001-ios-auth
aors=1001-ios-aor
direct_media=no
```

## extensions.conf - Dialplan

### Variante 1: Sequentiell (Empfohlen)

Erst SIPinator anpingen (Push ausloesen), dann iOS-Geraet klingeln lassen.

```ini
[from-internal]

; Anrufe an Extension 1001
exten => 1001,1,NoOp(Anruf fuer ${EXTEN})
 same => n,Set(__ORIGINAL_EXTEN=${EXTEN})

 ; SIPinator kurz anrufen (loest VoIP Push aus)
 ; X-Original-Extension Header mitgeben damit SIPinator weiss,
 ; welche Extension gemeint ist
 same => n,SIPAddHeader(X-Original-Extension: ${EXTEN})
 same => n,Dial(PJSIP/sipinator,2)

 ; Jetzt das iOS-Geraet klingeln lassen (30 Sekunden)
 same => n,Dial(PJSIP/1001-ios,30)

 ; Keine Antwort -> Voicemail
 same => n,VoiceMail(1001@default,u)
 same => n,Hangup()

; Gleiche Logik fuer weitere Extensions
exten => 1002,1,NoOp(Anruf fuer ${EXTEN})
 same => n,SIPAddHeader(X-Original-Extension: ${EXTEN})
 same => n,Dial(PJSIP/sipinator,2)
 same => n,Dial(PJSIP/1002-ios,30)
 same => n,VoiceMail(1002@default,u)
 same => n,Hangup()
```

### Variante 2: Pattern-basiert (fuer viele Extensions)

```ini
[from-internal]

; Alle Extensions 1000-1999
exten => _1XXX,1,NoOp(Anruf fuer ${EXTEN})
 same => n,SIPAddHeader(X-Original-Extension: ${EXTEN})
 same => n,Dial(PJSIP/sipinator,2)
 same => n,Dial(PJSIP/${EXTEN}-ios,30)
 same => n,VoiceMail(${EXTEN}@default,u)
 same => n,Hangup()
```

### Variante 3: Gleichzeitiges Klingeln

SIPinator und iOS-Geraet gleichzeitig klingeln lassen.
SIPinator antwortet sofort mit 486, was harmlos ist.

```ini
exten => _1XXX,1,NoOp(Anruf fuer ${EXTEN})
 same => n,SIPAddHeader(X-Original-Extension: ${EXTEN})
 same => n,Dial(PJSIP/sipinator&PJSIP/${EXTEN}-ios,30,r)
 same => n,VoiceMail(${EXTEN}@default,u)
 same => n,Hangup()
```

## Netzwerk

### SIPinator im Docker

- SIPinator lauscht auf UDP Port 5080 (SIP)
- Asterisk muss diesen Port erreichen koennen
- Bei Docker Bridge Networking: Port-Mapping `5080:5080/udp`
- Bei gleichem Host: `network_mode: host` oder Docker-IP verwenden

### Firewall

```bash
# SIPinator Ports oeffnen
ufw allow 5080/udp   # SIP (von Asterisk)
ufw allow 8080/tcp   # REST API (von iOS Apps)
```

### NAT Hinweis

Wenn SIPinator hinter NAT laeuft, muss Asterisk die korrekte IP kennen.
Am einfachsten: SIPinator und Asterisk im gleichen Netzwerk betreiben.

## Testen

### 1. SIP-Registrierung pruefen

```bash
# Auf Asterisk:
asterisk -rx "pjsip show registrations"

# Erwartete Ausgabe:
# sipinator/sip:sipinator@<docker-ip>:5080   sipinator   Registered
```

### 2. Endpunkt-Status

```bash
asterisk -rx "pjsip show endpoint sipinator"
```

### 3. Test-Anruf

Von einem SIP-Telefon die Extension 1001 anrufen.
In den SIPinator-Logs sollte erscheinen:

```
Incoming call: John Doe (1005) -> 1001
VoIP push sent to a1b2c3d4e5f6...
Call processed: push_result=success for 1001
```
