import 'package:flutter/foundation.dart';

/// Supported target environments for the Qbox application.
enum AppEnvironment {
  emulator,
  physicalDevice,
  localhost,
  production,
  custom,
}

/// Centralized environment and backend connectivity configuration for Qbox.
///
/// Configures backend connectivity across development platforms:
/// - Android emulator uses http://10.0.2.2:8000
/// - Physical Android phone uses http://192.168.1.5:8000
/// - Localhost/desktop/tests uses http://127.0.0.1:8000
/// - Production uses https://api.qbox.app (never leaks dev IPs)
///
/// Easily configured at compile time via --dart-define:
///   flutter run -d <device> --dart-define=TARGET_DEVICE=physical
///   flutter run -d <device> --dart-define=DEV_HOST_IP=192.168.1.5
///   flutter run -d <device> --dart-define=API_BASE_URL=http://192.168.1.5:8000
class AppConfig {
  AppConfig._();

  /// Default Wi-Fi host IPv4 for physical device development.
  /// Centralized here so it can be changed in a single place.
  static const String defaultDevHostIp = '192.168.1.5';
  static const int defaultDevPort = 8000;

  /// Android emulator loopback host to reach host PC.
  static const String emulatorHost = '10.0.2.2';

  /// Localhost for desktop/tests/web.
  static const String localhostHost = '127.0.0.1';

  /// Production base URL (clean domain, never hardcoded with dev IP).
  static const String productionBaseUrl = 'https://api.qbox.app';

  /// Compile-time environment overrides passed via --dart-define:
  static const String _definedBaseUrl = String.fromEnvironment('API_BASE_URL');
  static const String _definedTargetDevice = String.fromEnvironment('TARGET_DEVICE');
  static const String _definedDevHostIp = String.fromEnvironment('DEV_HOST_IP', defaultValue: defaultDevHostIp);
  static const int _definedDevPort = int.fromEnvironment('DEV_PORT', defaultValue: defaultDevPort);
  static const String _definedEnvironment = String.fromEnvironment('ENVIRONMENT', defaultValue: 'development');

  /// Dynamic runtime overrides (e.g. via in-app UI or test fixtures).
  static String? _runtimeBaseUrl;
  static AppEnvironment? _runtimeEnvironment;

  /// Sets runtime custom base URL.
  static void setBaseUrl(String url) {
    _runtimeBaseUrl = url.endsWith('/') ? url.substring(0, url.length - 1) : url;
  }

  /// Sets runtime active environment.
  static void setEnvironment(AppEnvironment env) {
    _runtimeEnvironment = env;
  }

  /// Clears runtime overrides, reverting to compile-time configuration.
  static void reset() {
    _runtimeBaseUrl = null;
    _runtimeEnvironment = null;
  }

  /// Active target device type (e.g. 'physical' or 'emulator').
  static String get targetDevice {
    if (_definedTargetDevice.isNotEmpty) {
      return _definedTargetDevice.toLowerCase();
    }
    return 'emulator';
  }

  /// Resolves the current active environment.
  static AppEnvironment get activeEnvironment {
    if (_runtimeEnvironment != null) return _runtimeEnvironment!;
    if (_runtimeBaseUrl != null && _runtimeBaseUrl!.isNotEmpty) return AppEnvironment.custom;
    if (_definedBaseUrl.isNotEmpty) return AppEnvironment.custom;
    if (_definedEnvironment.toLowerCase() == 'production') return AppEnvironment.production;

    if (targetDevice == 'physical' || targetDevice == 'physical_device' || targetDevice == 'phone') {
      return AppEnvironment.physicalDevice;
    }

    if (!kIsWeb && defaultTargetPlatform == TargetPlatform.android) {
      return AppEnvironment.emulator;
    }

    return AppEnvironment.localhost;
  }

  /// Gets the host IP used for physical device communication.
  static String get devHostIp => _definedDevHostIp;

  /// Gets the port used for backend communication.
  static int get devPort => _definedDevPort;

  /// Resolves the canonical backend base URL:
  /// 1. Runtime override (if set)
  /// 2. Explicit compile-time API_BASE_URL (if provided)
  /// 3. Production environment -> https://api.qbox.app
  /// 4. Physical device environment -> http://192.168.1.5:8000
  /// 5. Android emulator -> http://10.0.2.2:8000
  /// 6. Localhost/desktop/tests -> http://127.0.0.1:8000
  static String get baseUrl {
    if (_runtimeBaseUrl != null && _runtimeBaseUrl!.isNotEmpty) {
      return _runtimeBaseUrl!;
    }
    if (_definedBaseUrl.isNotEmpty) {
      return _definedBaseUrl.endsWith('/')
          ? _definedBaseUrl.substring(0, _definedBaseUrl.length - 1)
          : _definedBaseUrl;
    }

    switch (activeEnvironment) {
      case AppEnvironment.production:
        return productionBaseUrl;
      case AppEnvironment.physicalDevice:
        return 'http://$devHostIp:$devPort';
      case AppEnvironment.emulator:
        return 'http://$emulatorHost:$devPort';
      case AppEnvironment.custom:
        return _runtimeBaseUrl ?? _definedBaseUrl;
      case AppEnvironment.localhost:
        return 'http://$localhostHost:$devPort';
    }
  }

  /// Friendly display label for UI / developer status displays.
  static String get environmentLabel {
    switch (activeEnvironment) {
      case AppEnvironment.production:
        return 'Production';
      case AppEnvironment.physicalDevice:
        return 'Physical Device ($devHostIp:$devPort)';
      case AppEnvironment.emulator:
        return 'Android Emulator (10.0.2.2:$devPort)';
      case AppEnvironment.custom:
        return 'Custom ($baseUrl)';
      case AppEnvironment.localhost:
        return 'Localhost ($localhostHost:$devPort)';
    }
  }
}

