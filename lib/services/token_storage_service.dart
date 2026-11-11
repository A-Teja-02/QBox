import 'dart:convert';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import '../models/profiles.dart';

/// Thrown when hardware-backed secure storage (Android KeyStore / iOS Keychain) fails in production.
class SecureStorageException implements Exception {
  const SecureStorageException(this.message, [this.cause]);
  final String message;
  final Object? cause;

  @override
  String toString() => 'SecureStorageException: $message${cause != null ? ' ($cause)' : ''}';
}

/// Secure token and profile storage backed by Android Keystore / iOS Keychain via flutter_secure_storage.
///
/// In production Android and iOS environments, this service strictly uses hardware-backed secure storage.
/// In automated test environments (FLUTTER_TEST), it provides an in-memory test store.
/// Production builds NEVER silently fall back to unencrypted RAM storage if hardware security fails.
class TokenStorageService {
  TokenStorageService({FlutterSecureStorage? storage})
      : _storage = storage ??
            const FlutterSecureStorage(
              aOptions: AndroidOptions(resetOnError: true),
              iOptions: IOSOptions(accessibility: KeychainAccessibility.first_unlock),
            );

  final FlutterSecureStorage _storage;

  static const _keyAccessToken = 'qbox_secure_access_token';
  static const _keyRefreshToken = 'qbox_secure_refresh_token';
  static const _keyShopkeeperProfile = 'qbox_secure_shopkeeper_profile';
  static const _keyCustomerProfile = 'qbox_secure_customer_profile';
  static const _keyActiveRole = 'qbox_secure_active_role';
  static const _keyPendingShopToken = 'qbox_secure_pending_shop_token';

  // In-memory fallback used strictly in automated test environments
  static final Map<String, String> _testMemoryStore = {};

  /// Allows automated test suites to simulate production environment (!isTestEnvironment).
  @visibleForTesting
  static bool? testEnvironmentOverride;

  /// Visible for testing to verify whether memory store has been populated or touched.
  @visibleForTesting
  static Map<String, String> get testMemoryStore => _testMemoryStore;

  static bool get isTestEnvironment {
    if (testEnvironmentOverride != null) {
      return testEnvironmentOverride!;
    }
    try {
      return Platform.environment.containsKey('FLUTTER_TEST');
    } catch (_) {
      return false;
    }
  }

  /// Persists authentication tokens securely on the device.
  /// Throws [SecureStorageException] in production if hardware storage is unavailable.
  Future<void> saveTokens({
    required String accessToken,
    required String refreshToken,
  }) async {
    if (isTestEnvironment) {
      _testMemoryStore[_keyAccessToken] = accessToken;
      _testMemoryStore[_keyRefreshToken] = refreshToken;
      return;
    }

    try {
      await _storage.write(key: _keyAccessToken, value: accessToken);
      await _storage.write(key: _keyRefreshToken, value: refreshToken);
    } catch (e) {
      throw SecureStorageException(
        'Hardware-backed secure storage is unavailable. Token persistence aborted for security.',
        e,
      );
    }
  }

  /// Retrieves the persisted access token. Fails safely (returns null) if storage is unavailable.
  Future<String?> getAccessToken() async {
    if (isTestEnvironment) {
      return _testMemoryStore[_keyAccessToken];
    }
    try {
      return await _storage.read(key: _keyAccessToken);
    } catch (_) {
      // In production, never fall back to RAM memory store. Fail safely.
      return null;
    }
  }

  /// Retrieves the persisted refresh token. Fails safely (returns null) if storage is unavailable.
  Future<String?> getRefreshToken() async {
    if (isTestEnvironment) {
      return _testMemoryStore[_keyRefreshToken];
    }
    try {
      return await _storage.read(key: _keyRefreshToken);
    } catch (_) {
      // In production, never fall back to RAM memory store. Fail safely.
      return null;
    }
  }

  /// Saves the authenticated shopkeeper profile to secure storage.
  /// Throws [SecureStorageException] in production if hardware storage is unavailable.
  Future<void> saveShopkeeperProfile(ShopkeeperProfile profile) async {
    final payload = {
      'full_name': profile.fullName,
      'shop_name': profile.shopName,
      'shop_address': profile.shopAddress,
      'phone': profile.phone,
      'email': profile.email,
      'upi_id': profile.upiId,
      'qr_code_name': profile.qrCodeName,
      'user_id': profile.userId,
      'shop_id': profile.shopId,
    };
    final jsonStr = jsonEncode(payload);

    if (isTestEnvironment) {
      _testMemoryStore[_keyShopkeeperProfile] = jsonStr;
      return;
    }

    try {
      await _storage.write(key: _keyShopkeeperProfile, value: jsonStr);
    } catch (e) {
      throw SecureStorageException(
        'Hardware-backed secure storage is unavailable. Profile persistence aborted.',
        e,
      );
    }
  }

  /// Reads the persisted shopkeeper profile. Fails safely (returns null) if storage is unavailable.
  Future<ShopkeeperProfile?> getShopkeeperProfile() async {
    String? rawJson;
    if (isTestEnvironment) {
      rawJson = _testMemoryStore[_keyShopkeeperProfile];
    } else {
      try {
        rawJson = await _storage.read(key: _keyShopkeeperProfile);
      } catch (_) {
        return null;
      }
    }

    if (rawJson == null || rawJson.isEmpty) return null;
    try {
      final map = jsonDecode(rawJson) as Map<String, dynamic>;
      final accessToken = await getAccessToken();
      return ShopkeeperProfile(
        fullName: map['full_name'] as String? ?? '',
        shopName: map['shop_name'] as String? ?? '',
        shopAddress: map['shop_address'] as String? ?? '',
        phone: map['phone'] as String? ?? '',
        email: map['email'] as String?,
        upiId: map['upi_id'] as String?,
        qrCodeName: map['qr_code_name'] as String?,
        userId: map['user_id'] as String?,
        shopId: map['shop_id'] as String?,
        accessToken: accessToken,
      );
    } catch (_) {
      return null;
    }
  }

  /// Saves the active role in secure storage.
  /// Throws [SecureStorageException] in production if hardware storage is unavailable.
  Future<void> saveActiveRole(String role) async {
    if (isTestEnvironment) {
      _testMemoryStore[_keyActiveRole] = role;
      return;
    }

    try {
      await _storage.write(key: _keyActiveRole, value: role);
    } catch (e) {
      throw SecureStorageException('Hardware-backed secure storage is unavailable. Role persistence aborted.', e);
    }
  }

  /// Retrieves the persisted active role. Fails safely (returns null) if storage is unavailable.
  Future<String?> getActiveRole() async {
    if (isTestEnvironment) {
      return _testMemoryStore[_keyActiveRole];
    }
    try {
      return await _storage.read(key: _keyActiveRole);
    } catch (_) {
      return null;
    }
  }

  /// Saves the authenticated customer profile to secure storage.
  /// Throws [SecureStorageException] in production if hardware storage is unavailable.
  Future<void> saveCustomerProfile(RegisteredCustomer profile) async {
    final payload = {
      'full_name': profile.fullName,
      'phone': profile.phone,
      'address': profile.address,
      'user_id': profile.userId,
    };
    final jsonStr = jsonEncode(payload);

    if (isTestEnvironment) {
      _testMemoryStore[_keyCustomerProfile] = jsonStr;
      return;
    }

    try {
      await _storage.write(key: _keyCustomerProfile, value: jsonStr);
    } catch (e) {
      throw SecureStorageException('Hardware-backed secure storage is unavailable. Profile persistence aborted.', e);
    }
  }

  /// Reads the persisted customer profile. Fails safely (returns null) if storage is unavailable.
  Future<RegisteredCustomer?> getCustomerProfile() async {
    String? rawJson;
    if (isTestEnvironment) {
      rawJson = _testMemoryStore[_keyCustomerProfile];
    } else {
      try {
        rawJson = await _storage.read(key: _keyCustomerProfile);
      } catch (_) {
        return null;
      }
    }

    if (rawJson == null || rawJson.isEmpty) return null;
    try {
      final map = jsonDecode(rawJson) as Map<String, dynamic>;
      final accessToken = await getAccessToken();
      return RegisteredCustomer(
        fullName: map['full_name'] as String? ?? '',
        phone: map['phone'] as String? ?? '',
        address: map['address'] as String? ?? '',
        userId: map['user_id'] as String?,
        accessToken: accessToken,
      );
    } catch (_) {
      return null;
    }
  }

  /// Wipes all stored tokens and sessions from secure hardware storage.
  Future<void> clearAll() async {
    if (isTestEnvironment) {
      _testMemoryStore.clear();
      return;
    }

    try {
      await _storage.deleteAll();
    } catch (e) {
      throw SecureStorageException('Hardware-backed secure storage clear failed.', e);
    }
  }

  /// Persists a pending shop registration QR token during customer signup/login.
  Future<void> savePendingShopToken(String token) async {
    if (isTestEnvironment) {
      _testMemoryStore[_keyPendingShopToken] = token;
      return;
    }
    try {
      await _storage.write(key: _keyPendingShopToken, value: token);
    } catch (e) {
      throw SecureStorageException('Hardware-backed secure storage is unavailable. Token persistence aborted.', e);
    }
  }

  /// Retrieves the pending shop registration QR token if one exists.
  Future<String?> getPendingShopToken() async {
    if (isTestEnvironment) {
      return _testMemoryStore[_keyPendingShopToken];
    }
    try {
      return await _storage.read(key: _keyPendingShopToken);
    } catch (_) {
      return null;
    }
  }

  /// Clears the pending shop registration QR token after connection completes or cancels.
  Future<void> clearPendingShopToken() async {
    if (isTestEnvironment) {
      _testMemoryStore.remove(_keyPendingShopToken);
      return;
    }
    try {
      await _storage.delete(key: _keyPendingShopToken);
    } catch (_) {}
  }
}
