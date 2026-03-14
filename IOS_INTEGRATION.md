# SIPinator - iOS App Integration Guide

## Uebersicht

Die iOS App muss folgende Aufgaben uebernehmen:

1. **PushKit registrieren** und VoIP Push Token erhalten
2. **Token beim SIPinator Server registrieren** (REST API)
3. **VoIP Push empfangen** und sofort an CallKit melden
4. **Direkte SIP-Verbindung** zu Asterisk aufbauen fuer den eigentlichen Anruf

## REST API Endpunkte

**Base URL:** `http://<server-ip>:8080`

Alle Endpunkte (ausser Health Check) erfordern:
```
Authorization: Bearer <API_SECRET_KEY>
```

### POST /api/v1/tokens - Push Token registrieren

Nach PushKit-Registrierung diesen Endpunkt aufrufen.

```
POST /api/v1/tokens
Content-Type: application/json
Authorization: Bearer <API_SECRET_KEY>

{
  "device_token": "<hex-push-token>",
  "sip_extension": "1001",
  "app_bundle_id": "com.example.sipinator"
}
```

**Response (201):**
```json
{
  "id": 1,
  "device_token": "<hex-push-token>",
  "sip_extension": "1001",
  "app_bundle_id": "com.example.sipinator",
  "created_at": "2026-03-14T12:00:00"
}
```

**Hinweis:** `sip_extension` ist die Extension des Benutzers auf der Asterisk-PBX
(z.B. "1001"). Diese muss mit der Asterisk-Konfiguration uebereinstimmen.

### DELETE /api/v1/tokens - Push Token entfernen

Bei Logout oder Token-Erneuerung aufrufen.

```
DELETE /api/v1/tokens
Content-Type: application/json
Authorization: Bearer <API_SECRET_KEY>

{
  "device_token": "<hex-push-token>"
}
```

**Response (200):**
```json
{"message": "Token unregistered"}
```

### GET /api/v1/health - Health Check

Kein Auth noetig. Kann zur Verbindungspruefung genutzt werden.

```
GET /api/v1/health
```

**Response (200):**
```json
{
  "status": "ok",
  "sip_registered": true,
  "apns_configured": true,
  "active_tokens": 5,
  "uptime_seconds": 3600.0,
  "version": "1.0.0"
}
```

## VoIP Push Payload Format

Die iOS App empfaengt folgenden Payload via PushKit:

```json
{
  "aps": {},
  "caller_id": "1005",
  "caller_name": "John Doe",
  "call_uuid": "550e8400-e29b-41d4-a716-446655440000",
  "sip_extension": "1001",
  "server_host": "192.168.1.100",
  "timestamp": 1710000000
}
```

| Feld | Typ | Beschreibung |
|------|-----|-------------|
| `aps` | Object | Leer, wird fuer VoIP Push benoetigt |
| `caller_id` | String | Telefonnummer/Extension des Anrufers |
| `caller_name` | String | Anzeigename des Anrufers (falls verfuegbar) |
| `call_uuid` | String | Eindeutige UUID fuer diesen Anruf |
| `sip_extension` | String | Gerufene Extension (des Benutzers) |
| `server_host` | String | Asterisk-Server IP/Hostname |
| `timestamp` | Int | Unix Timestamp des Anrufs |

## iOS Implementation

### 1. PushKit registrieren

```swift
import PushKit

class AppDelegate: UIResponder, UIApplicationDelegate {
    let pushRegistry = PKPushRegistry(queue: DispatchQueue.main)

    func application(_ application: UIApplication,
                     didFinishLaunchingWithOptions launchOptions: ...) -> Bool {
        pushRegistry.delegate = self
        pushRegistry.desiredPushTypes = [.voIP]
        return true
    }
}
```

### 2. Push Token an Server senden

```swift
extension AppDelegate: PKPushRegistryDelegate {
    func pushRegistry(_ registry: PKPushRegistry,
                      didUpdate pushCredentials: PKPushCredentials,
                      for type: PKPushType) {
        let token = pushCredentials.token
            .map { String(format: "%02x", $0) }
            .joined()

        Task {
            try await SIPinatorAPI.shared.registerToken(
                deviceToken: token,
                sipExtension: UserSettings.sipExtension,  // z.B. "1001"
                bundleId: Bundle.main.bundleIdentifier!
            )
        }
    }
}
```

### 3. VoIP Push empfangen + CallKit

**WICHTIG (iOS 13+):** `reportNewIncomingCall` MUSS sofort aufgerufen werden,
bevor die `completion` des Push-Handlers zurueckkehrt. Sonst beendet iOS die App.

```swift
func pushRegistry(_ registry: PKPushRegistry,
                  didReceiveIncomingPushWith payload: PKPushPayload,
                  for type: PKPushType,
                  completion: @escaping () -> Void) {
    guard type == .voIP else {
        completion()
        return
    }

    let data = payload.dictionaryPayload
    let callerId = data["caller_id"] as? String ?? "Unknown"
    let callerName = data["caller_name"] as? String ?? callerId
    let callUUID = UUID(uuidString: data["call_uuid"] as? String ?? "") ?? UUID()
    let sipExtension = data["sip_extension"] as? String ?? ""
    let serverHost = data["server_host"] as? String ?? ""

    // CallKit sofort informieren
    let update = CXCallUpdate()
    update.remoteHandle = CXHandle(type: .phoneNumber, value: callerId)
    update.localizedCallerName = callerName
    update.hasVideo = false

    callProvider.reportNewIncomingCall(with: callUUID, update: update) { error in
        if let error = error {
            print("CallKit error: \(error)")
        } else {
            // SIP-Verbindung zu Asterisk aufbauen
            SIPManager.shared.connectToAsterisk(
                host: serverHost,
                extension: sipExtension,
                callUUID: callUUID
            )
        }
        completion()
    }
}
```

### 4. API Client

```swift
class SIPinatorAPI {
    static let shared = SIPinatorAPI()

    private let baseURL: URL
    private let apiKey: String

    init() {
        self.baseURL = URL(string: "http://\(ServerConfig.host):8080")!
        self.apiKey = ServerConfig.apiKey
    }

    func registerToken(deviceToken: String,
                       sipExtension: String,
                       bundleId: String) async throws {
        var request = URLRequest(
            url: baseURL.appendingPathComponent("api/v1/tokens")
        )
        request.httpMethod = "POST"
        request.setValue("Bearer \(apiKey)",
                        forHTTPHeaderField: "Authorization")
        request.setValue("application/json",
                        forHTTPHeaderField: "Content-Type")

        let body: [String: String] = [
            "device_token": deviceToken,
            "sip_extension": sipExtension,
            "app_bundle_id": bundleId,
        ]
        request.httpBody = try JSONEncoder().encode(body)

        let (_, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse,
              (200...299).contains(http.statusCode) else {
            throw APIError.registrationFailed
        }
    }

    func unregisterToken(deviceToken: String) async throws {
        var request = URLRequest(
            url: baseURL.appendingPathComponent("api/v1/tokens")
        )
        request.httpMethod = "DELETE"
        request.setValue("Bearer \(apiKey)",
                        forHTTPHeaderField: "Authorization")
        request.setValue("application/json",
                        forHTTPHeaderField: "Content-Type")

        let body = ["device_token": deviceToken]
        request.httpBody = try JSONEncoder().encode(body)

        let (_, _) = try await URLSession.shared.data(for: request)
    }

    func healthCheck() async throws -> Bool {
        let url = baseURL.appendingPathComponent("api/v1/health")
        let (data, _) = try await URLSession.shared.data(from: url)
        let json = try JSONDecoder().decode(HealthResponse.self, from: data)
        return json.status == "ok"
    }
}

struct HealthResponse: Codable {
    let status: String
    let sipRegistered: Bool
    let apnsConfigured: Bool
    let activeTokens: Int

    enum CodingKeys: String, CodingKey {
        case status
        case sipRegistered = "sip_registered"
        case apnsConfigured = "apns_configured"
        case activeTokens = "active_tokens"
    }
}

enum APIError: Error {
    case registrationFailed
}
```

## Ablauf zusammengefasst

```
1. App startet -> PushKit registrieren -> Token erhalten
2. Token + SIP Extension an SIPinator Server senden (POST /api/v1/tokens)
3. Eingehender Anruf auf Asterisk
4. Asterisk -> INVITE an SIPinator -> SIPinator sendet VoIP Push
5. iOS App empfaengt Push -> CallKit reportNewIncomingCall()
6. Benutzer nimmt an -> App verbindet sich direkt mit Asterisk via SIP
7. Gespraech laeuft direkt zwischen iOS App und Asterisk (ohne SIPinator)
```

## Voraussetzungen

- Apple Developer Account mit VoIP Push Capability
- `.p8` Auth Key von Apple Developer Portal (Keys -> Create)
- App muss `PushKit.framework` und `CallKit.framework` einbinden
- Background Mode "Voice over IP" in Xcode aktivieren
- Die `sip_extension` muss mit der Asterisk-Konfiguration uebereinstimmen
