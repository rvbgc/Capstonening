/// Address of the SMISHGUARD backend used by every request in the app.
///
/// The default works on the Android emulator, where 10.0.2.2 points to the
/// Windows PC that runs the backend.
///
/// For a physical phone on the same Wi-Fi, build with the PC's address:
///
///   flutter build apk --debug --dart-define=API_BASE_URL=http://192.168.1.23:8000
const String apiBaseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'http://10.0.2.2:8000',
);
