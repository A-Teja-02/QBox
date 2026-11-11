# Qbox Shopkeeper Android Demo

A small Flutter demo with sample customers and an in-memory Udhaar ledger.

## Run on Windows

1. Extract this folder.
2. Open PowerShell in this folder.
3. Run `flutter pub get`.
4. Run `flutter devices` and start an Android emulator from Android Studio if needed.
5. Run `flutter run`.

To run the money-formatting test: `flutter test`.

## Demo limitations

- Sample data is stored in memory and resets when the app restarts.
- No backend, real authentication, cloud sync, customer app, or payment integration.
- This is a demo only, not suitable for real financial records.
- Money is represented as integer paise; decimal strings are parsed without floating-point arithmetic.
