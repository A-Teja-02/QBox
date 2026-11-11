import 'dart:async';
import 'package:flutter/services.dart';

/// Service managing deep-link processing and incoming registration tokens.
///
/// Supports:
/// - Custom Android Scheme: `qbox://join/{token}`
/// - Android Intent URI: `intent://join/{token}#Intent;scheme=qbox;package=com.example.qbox_shopkeeper_demo;end`
/// - HTTP/HTTPS Web URL: `http://192.168.1.5:8000/join/{token}` or `https://qbox.app/join/{token}`
/// - Query Parameter: `qbox://join?token={token}` or `http://.../join?token={token}`
class DeepLinkService {
  DeepLinkService({MethodChannel? channel})
      : _channel = channel ?? const MethodChannel('com.example.qbox/deeplink');

  final MethodChannel _channel;
  bool _initialized = false;

  /// Extracts and validates the registration token from any supported raw URL or URI string.
  /// Returns null if the URL is empty, invalid, malformed, or contains no token.
  static String? extractToken(String? rawUrl) {
    if (rawUrl == null) return null;
    final trimmed = rawUrl.trim();
    if (trimmed.isEmpty) return null;

    String normalized = trimmed;

    // Handle android intent:// URIs from mobile Chrome / Samsung Internet
    // Format: intent://join/TOKEN#Intent;scheme=qbox;package=com.example.qbox_shopkeeper_demo;end
    if (normalized.startsWith('intent://')) {
      final hashIdx = normalized.indexOf('#Intent');
      if (hashIdx != -1) {
        normalized = 'qbox://' + normalized.substring(9, hashIdx);
      } else {
        normalized = 'qbox://' + normalized.substring(9);
      }
    }

    final uri = Uri.tryParse(normalized);
    if (uri == null) return null;

    // 1. Explicit query parameter ?token=...
    if (uri.queryParameters.containsKey('token')) {
      final t = uri.queryParameters['token']!.trim();
      if (t.isNotEmpty) return _sanitizeToken(t);
    }

    // 2. Custom scheme: qbox://join/{token}
    if (uri.scheme == 'qbox') {
      if (uri.host.toLowerCase() == 'join') {
        if (uri.pathSegments.isNotEmpty) {
          final t = uri.pathSegments.first.trim();
          if (t.isNotEmpty) return _sanitizeToken(t);
        }
      }
      final joinIdx = uri.pathSegments.indexWhere((s) => s.toLowerCase() == 'join');
      if (joinIdx != -1 && joinIdx + 1 < uri.pathSegments.length) {
        final t = uri.pathSegments[joinIdx + 1].trim();
        if (t.isNotEmpty) return _sanitizeToken(t);
      }
      return null;
    }

    // 3. Web URL: http://<ip_or_host>:<port>/join/{token} or https://qbox.app/join/{token}
    if (uri.scheme == 'http' || uri.scheme == 'https') {
      final joinIdx = uri.pathSegments.indexWhere((s) => s.toLowerCase() == 'join');
      if (joinIdx != -1 && joinIdx + 1 < uri.pathSegments.length) {
        final t = uri.pathSegments[joinIdx + 1].trim();
        if (t.isNotEmpty) return _sanitizeToken(t);
      }
      return null;
    }

    // 4. Raw fallback if input is just a plain token string without scheme or path
    if (!trimmed.contains('://') && !trimmed.contains('/')) {
      return _sanitizeToken(trimmed);
    }

    return null;
  }

  static String? _sanitizeToken(String token) {
    var clean = token.split('#').first.split('?').first.trim();
    while (clean.endsWith('/')) {
      clean = clean.substring(0, clean.length - 1);
    }
    if (clean.isEmpty || clean.toLowerCase() == 'join') return null;
    return clean;
  }

  /// Sets up method call handling for incoming deep links and checks for cold-start initial links.
  Future<void> initialize({required void Function(String token) onTokenReceived}) async {
    if (_initialized) return;
    _initialized = true;

    _channel.setMethodCallHandler((call) async {
      if (call.method == 'onNewDeepLink' && call.arguments is String) {
        final raw = call.arguments as String;
        final token = extractToken(raw);
        if (token != null) {
          onTokenReceived(token);
        }
      }
    });

    // Check cold-start initial link if app was launched directly from browser
    try {
      final initialUrl = await _channel.invokeMethod<String>('getInitialDeepLink');
      if (initialUrl != null && initialUrl.isNotEmpty) {
        final token = extractToken(initialUrl);
        if (token != null) {
          onTokenReceived(token);
        }
      }
    } catch (_) {
      // Handled safely in tests or headless platforms
    }
  }
}
