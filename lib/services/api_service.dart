
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'package:http/http.dart' as http;
import '../config/app_config.dart';
import '../models/profiles.dart';

/// Result wrapper for API operations.
class ApiResult<T> {
  const ApiResult._({
    this.data,
    this.errorMessage,
    required this.isSuccess,
    this.isNetworkError = false,
  });

  final T? data;
  final String? errorMessage;
  final bool isSuccess;
  final bool isNetworkError;

  factory ApiResult.success(T data) => ApiResult._(data: data, isSuccess: true);
  factory ApiResult.failure(String error, {bool isNetworkError = false}) =>
      ApiResult._(errorMessage: error, isSuccess: false, isNetworkError: isNetworkError);
}

/// Login response payload containing tokens and profile data.
class LoginResultData {
  LoginResultData({
    required this.accessToken,
    required this.refreshToken,
    required this.roles,
    required this.profile,
  });

  final String accessToken;
  final String refreshToken;
  final List<String> roles;
  final ShopkeeperProfile profile;
}

/// Service managing communication with the Qbox FastAPI backend.
class ApiService {
  ApiService({http.Client? client}) : _client = client ?? http.Client();

  final http.Client _client;

  /// Mock client provider for widget tests or offline demo.
  static ApiService? mockInstance;

  /// Optional mock result override for testing customer list scenarios (e.g. empty, error, populated).
  static ApiResult<List<ShopCustomerItem>>? mockShopCustomersResult;

  /// Optional mock result override for login requests.
  static ApiResult<LoginResultData>? mockLoginResult;

  /// Optional mock result override for shopkeeper registration requests.
  static ApiResult<ShopkeeperProfile>? mockShopkeeperRegisterResult;

  /// Optional mock result override for customer registration requests.
  static ApiResult<RegisteredCustomer>? mockCustomerRegisterResult;

  /// Resets all test mock overrides.
  static void resetTestMocks() {
    mockInstance = null;
    mockShopCustomersResult = null;
    mockLoginResult = null;
    mockShopkeeperRegisterResult = null;
    mockCustomerRegisterResult = null;
  }

  /// When true, forces live HTTP requests even when running inside flutter test.
  static bool enableLiveHttpInTests = false;

  static bool get isTestEnvironment {
    try {
      return Platform.environment.containsKey('FLUTTER_TEST');
    } catch (_) {
      return false;
    }
  }

  /// Sets custom base URL override on centralized AppConfig.
  static void setBaseUrl(String url) {
    AppConfig.setBaseUrl(url);
  }

  /// Resolves the backend base URL from centralized AppConfig:
  /// - Physical device uses http://192.168.1.5:8000
  /// - Android emulator uses http://10.0.2.2:8000
  /// - Tests / desktop use http://127.0.0.1:8000
  /// - Production uses https://api.qbox.app
  static String get defaultBaseUrl => AppConfig.baseUrl;

  /// Builds standard API request headers with environment metadata.
  static Map<String, String> buildHeaders({String? authToken, bool json = true}) {
    final headers = <String, String>{};
    if (json) {
      headers['Content-Type'] = 'application/json';
    }
    if (authToken != null && authToken.isNotEmpty) {
      headers['Authorization'] = 'Bearer $authToken';
    }
    headers['X-Client-Device'] = AppConfig.activeEnvironment == AppEnvironment.physicalDevice
        ? 'physical'
        : 'emulator';
    return headers;
  }

  /// Sends registration request to the backend.
  Future<ApiResult<ShopkeeperProfile>> registerShopkeeper({
    required String fullName,
    required String shopName,
    required String shopAddress,
    required String phone,
    required String password,
    String? email,
    String? upiId,
    String? qrImageUrl,
    String? paymentQrFilePath,
    List<int>? paymentQrBytes,
    String? paymentQrFileName,
  }) async {
    if (mockShopkeeperRegisterResult != null) {
      return mockShopkeeperRegisterResult!;
    }

    if (mockInstance != null) {
      return mockInstance!.registerShopkeeper(
        fullName: fullName,
        shopName: shopName,
        shopAddress: shopAddress,
        phone: phone,
        password: password,
        email: email,
        upiId: upiId,
        qrImageUrl: qrImageUrl,
        paymentQrFilePath: paymentQrFilePath,
        paymentQrBytes: paymentQrBytes,
        paymentQrFileName: paymentQrFileName,
      );
    }

    if (isTestEnvironment && !enableLiveHttpInTests) {
      return ApiResult.failure(
        'Backend connection unavailable in headless test environment.',
        isNetworkError: true,
      );
    }

    final url = Uri.parse('$defaultBaseUrl/api/v1/auth/register/shopkeeper');

    try {
      http.Response response;

      if (paymentQrFilePath != null || paymentQrBytes != null) {
        // Send multipart request
        final request = http.MultipartRequest('POST', url);
        request.headers.addAll(buildHeaders());
        request.fields['full_name'] = fullName.trim();
        request.fields['shop_name'] = shopName.trim();
        request.fields['shop_address'] = shopAddress.trim();
        request.fields['phone'] = phone.trim();
        request.fields['password'] = password;
        if (email != null && email.trim().isNotEmpty) request.fields['email'] = email.trim();
        if (upiId != null && upiId.trim().isNotEmpty) request.fields['upi_id'] = upiId.trim();

        if (paymentQrFilePath != null) {
          request.files.add(await http.MultipartFile.fromPath('payment_qr_image', paymentQrFilePath));
        } else if (paymentQrBytes != null) {
          request.files.add(http.MultipartFile.fromBytes(
            'payment_qr_image',
            paymentQrBytes,
            filename: paymentQrFileName ?? 'payment_qr.png',
          ));
        }

        final streamed = await _client.send(request).timeout(const Duration(seconds: 15));
        response = await http.Response.fromStream(streamed);
      } else {
        // Fallback JSON payload
        final payload = {
          'full_name': fullName.trim(),
          'shop_name': shopName.trim(),
          'shop_address': shopAddress.trim(),
          'phone': phone.trim(),
          'password': password,
          if (email != null && email.trim().isNotEmpty) 'email': email.trim(),
          if (upiId != null && upiId.trim().isNotEmpty) 'upi_id': upiId.trim(),
          if (qrImageUrl != null && qrImageUrl.trim().isNotEmpty) 'qr_image_url': qrImageUrl.trim(),
        };

        response = await _client.post(
          url,
          headers: buildHeaders(),
          body: jsonEncode(payload),
        ).timeout(const Duration(seconds: 10));
      }

      if (response.statusCode == 201) {
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        final tokenMap = data['tokens'] as Map<String, dynamic>?;
        final accessToken = tokenMap?['access_token'] as String?;
        final refreshToken = tokenMap?['refresh_token'] as String?;
        final profile = ShopkeeperProfile(
          fullName: data['full_name'] as String? ?? fullName,
          shopName: data['shop_name'] as String? ?? shopName,
          shopAddress: data['shop_address'] as String? ?? shopAddress,
          phone: data['phone'] as String? ?? phone,
          email: data['email'] as String? ?? email,
          upiId: data['upi_id'] as String? ?? upiId,
          qrCodeName: (data['qr_image_url'] ?? data['qr_image_path']) as String? ?? qrImageUrl,
          userId: (data['user_id'] ?? data['id'])?.toString(),
          shopId: data['shop_id']?.toString(),
          accessToken: accessToken,
          refreshToken: refreshToken,
          paymentQrUrl: data['payment_qr_url'] as String?,
          hasPaymentQr: data['has_payment_qr'] as bool? ?? false,
        );
        return ApiResult.success(profile);
      } else {
        final errorMsg = _extractErrorMessage(response);
        return ApiResult.failure(errorMsg);
      }
    } on SocketException catch (_) {
      return ApiResult.failure('Cannot connect to Qbox server at $defaultBaseUrl. Please check your network or ensure backend is running.', isNetworkError: true);
    } on http.ClientException catch (e) {
      return ApiResult.failure('Network connection error: ${e.message}', isNetworkError: true);
    } catch (e) {
      return ApiResult.failure('Cannot connect to Qbox server at $defaultBaseUrl. ($e)', isNetworkError: true);
    }
  }

  /// Authenticates using identifier (mobile or email) and password.
  Future<ApiResult<LoginResultData>> login({
    required String identifier,
    required String password,
  }) async {
    if (mockLoginResult != null) {
      return mockLoginResult!;
    }

    if (mockInstance != null) {
      return mockInstance!.login(identifier: identifier, password: password);
    }

    if (isTestEnvironment && !enableLiveHttpInTests) {
      return ApiResult.failure(
        'Backend connection unavailable in headless test environment.',
        isNetworkError: true,
      );
    }

    final url = Uri.parse('$defaultBaseUrl/api/v1/auth/login');
    final payload = {
      'identifier': identifier.trim(),
      'password': password,
    };

    try {
      final response = await _client.post(
        url,
        headers: buildHeaders(),
        body: jsonEncode(payload),
      ).timeout(const Duration(seconds: 10));

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        final user = data['user'] as Map<String, dynamic>? ?? {};
        final profileMap = data['shopkeeper_profile'] as Map<String, dynamic>? ?? {};
        final shopMap = data['shop'] as Map<String, dynamic>? ?? {};
        final rawRoles = data['roles'] as List<dynamic>? ?? [];
        final roles = rawRoles.map((r) => r.toString()).toList();

        final fullName = (data['full_name'] ?? profileMap['full_name']) as String? ?? 'Shopkeeper';
        final shopName = (data['shop_name'] ?? shopMap['name'] ?? shopMap['shop_name']) as String? ?? 'My Shop';
        final shopAddress = (data['shop_address'] ?? shopMap['address'] ?? shopMap['shop_address']) as String? ?? '';
        final phone = (data['phone'] ?? user['phone']) as String? ?? identifier;
        final email = (data['email'] ?? user['email']) as String?;
        final upiId = (data['upi_id'] ?? shopMap['upi_id']) as String?;
        final qrCodeName = (data['qr_image_url'] ?? shopMap['qr_image_url'] ?? shopMap['qr_image_path']) as String?;
        final userId = (data['user_id'] ?? user['id'])?.toString();
        final shopId = (data['shop_id'] ?? shopMap['id'])?.toString();
        final accessToken = data['access_token'] as String? ?? '';
        final refreshToken = data['refresh_token'] as String? ?? '';

        final profile = ShopkeeperProfile(
          fullName: fullName,
          shopName: shopName,
          shopAddress: shopAddress,
          phone: phone,
          email: email,
          upiId: upiId,
          qrCodeName: qrCodeName,
          userId: userId,
          shopId: shopId,
          accessToken: accessToken,
        );

        return ApiResult.success(LoginResultData(
          accessToken: accessToken,
          refreshToken: refreshToken,
          roles: roles,
          profile: profile,
        ));
      } else {
        final errorMsg = _extractErrorMessage(response);
        return ApiResult.failure(errorMsg);
      }
    } on SocketException catch (_) {
      return ApiResult.failure('Cannot connect to Qbox server at $defaultBaseUrl. Please check your network or ensure backend is running.', isNetworkError: true);
    } on http.ClientException catch (e) {
      return ApiResult.failure('Network connection error: ${e.message}', isNetworkError: true);
    } catch (e) {
      return ApiResult.failure('Cannot connect to Qbox server at $defaultBaseUrl. ($e)', isNetworkError: true);
    }
  }

  /// Registers a customer in PostgreSQL.
  Future<ApiResult<RegisteredCustomer>> registerCustomer({
    required String fullName,
    required String phone,
    required String password,
    String? address,
  }) async {
    if (mockCustomerRegisterResult != null) {
      return mockCustomerRegisterResult!;
    }

    if (mockInstance != null) {
      return mockInstance!.registerCustomer(
        fullName: fullName,
        phone: phone,
        password: password,
        address: address,
      );
    }

    if (isTestEnvironment && !enableLiveHttpInTests) {
      return ApiResult.failure(
        'Backend connection unavailable in headless test environment.',
        isNetworkError: true,
      );
    }

    final url = Uri.parse('$defaultBaseUrl/api/v1/customer/register');
    final payload = {
      'full_name': fullName.trim(),
      'phone': phone.trim(),
      'password': password,
      if (address != null && address.trim().isNotEmpty) 'address': address.trim(),
    };

    try {
      final response = await _client.post(
        url,
        headers: buildHeaders(),
        body: jsonEncode(payload),
      ).timeout(const Duration(seconds: 10));

      if (response.statusCode == 201) {
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        final cust = RegisteredCustomer(
          fullName: data['full_name'] as String? ?? fullName,
          phone: data['phone'] as String? ?? phone,
          address: data['address'] as String? ?? (address ?? ''),
          userId: data['user_id']?.toString(),
          accessToken: data['access_token'] as String?,
          refreshToken: data['refresh_token'] as String?,
        );
        return ApiResult.success(cust);
      } else {
        return ApiResult.failure(_extractErrorMessage(response));
      }
    } on SocketException catch (_) {
      return ApiResult.failure('Cannot connect to Qbox server at $defaultBaseUrl.', isNetworkError: true);
    } catch (e) {
      return ApiResult.failure('Network error: $e', isNetworkError: true);
    }
  }

  /// Exchanges a refresh token for a fresh access token.
  Future<ApiResult<Map<String, dynamic>>> refreshAccessToken(String refreshToken) async {
    if (mockInstance != null) {
      return mockInstance!.refreshAccessToken(refreshToken);
    }

    if (isTestEnvironment && !enableLiveHttpInTests) {
      return ApiResult.failure(
        'Backend connection unavailable in headless test environment.',
        isNetworkError: true,
      );
    }

    final url = Uri.parse('$defaultBaseUrl/api/v1/auth/refresh');
    try {
      final response = await _client.post(
        url,
        headers: buildHeaders(),
        body: jsonEncode({'refresh_token': refreshToken}),
      ).timeout(const Duration(seconds: 10));

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        return ApiResult.success(data);
      } else {
        return ApiResult.failure(_extractErrorMessage(response));
      }
    } catch (e) {
      return ApiResult.failure('Failed to refresh authentication token: $e', isNetworkError: true);
    }
  }

  /// Invalidates the active authentication session server-side.
  Future<ApiResult<bool>> logout({
    required String authToken,
    String? refreshToken,
    bool allSessions = false,
  }) async {
    if (mockInstance != null) {
      return mockInstance!.logout(
        authToken: authToken,
        refreshToken: refreshToken,
        allSessions: allSessions,
      );
    }

    if (isTestEnvironment && !enableLiveHttpInTests) {
      return ApiResult.success(true);
    }

    final url = Uri.parse('$defaultBaseUrl/api/v1/auth/logout');
    try {
      final response = await _client.post(
        url,
        headers: buildHeaders(authToken: authToken),
        body: jsonEncode({
          if (refreshToken != null && refreshToken.isNotEmpty) 'refresh_token': refreshToken,
          'all_sessions': allSessions,
        }),
      ).timeout(const Duration(seconds: 10));

      if (response.statusCode == 200) {
        return ApiResult.success(true);
      } else {
        return ApiResult.failure(_extractErrorMessage(response));
      }
    } catch (e) {
      return ApiResult.failure('Logout failed: $e', isNetworkError: true);
    }
  }

  /// Retrieves the static customer registration QR for the authorized shopkeeper.
  /// If shopId is null, empty or 'me', resolves the authenticated user's shop automatically.
  Future<ApiResult<ShopRegistrationQrData>> getShopRegistrationQr(
    String? shopId, {
    required String authToken,
  }) async {
    if (mockInstance != null) {
      return mockInstance!.getShopRegistrationQr(shopId, authToken: authToken);
    }
    final effectiveShopId = (shopId == null || shopId.trim().isEmpty || shopId == 'me') ? 'me' : shopId.trim();

    if (isTestEnvironment && !enableLiveHttpInTests) {
      return ApiResult.success(ShopRegistrationQrData(
        shopId: effectiveShopId == 'me' ? 'demo-shop-id' : effectiveShopId,
        shopName: 'Demo Store',
        shopAddress: 'MG Road',
        registrationUrl: '$defaultBaseUrl/join/demo-token-12345',
        qrCodeSvg: '<svg></svg>',
        isActive: true,
        createdAt: DateTime.now().toIso8601String(),
      ));
    }

    final endpoint = effectiveShopId == 'me'
        ? '$defaultBaseUrl/api/v1/shops/me/registration-qr'
        : '$defaultBaseUrl/api/v1/shops/$effectiveShopId/registration-qr';

    final url = Uri.parse(endpoint);
    try {
      final response = await _client.get(
        url,
        headers: buildHeaders(authToken: authToken),
      ).timeout(const Duration(seconds: 10));

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        return ApiResult.success(ShopRegistrationQrData.fromJson(data));
      } else {
        return ApiResult.failure(_extractErrorMessage(response));
      }
    } catch (e) {
      return ApiResult.failure('Failed to load shop QR: $e', isNetworkError: true);
    }
  }

  /// Rotates the registration QR token for a shop.
  Future<ApiResult<ShopRegistrationQrData>> rotateShopRegistrationQr(
    String? shopId, {
    required String authToken,
  }) async {
    if (mockInstance != null) {
      return mockInstance!.rotateShopRegistrationQr(shopId, authToken: authToken);
    }
    final effectiveShopId = (shopId == null || shopId.trim().isEmpty || shopId == 'me') ? 'me' : shopId.trim();

    if (isTestEnvironment && !enableLiveHttpInTests) {
      return ApiResult.success(ShopRegistrationQrData(
        shopId: effectiveShopId == 'me' ? 'demo-shop-id' : effectiveShopId,
        shopName: 'Demo Store',
        shopAddress: 'MG Road',
        registrationUrl: '$defaultBaseUrl/join/rotated-token-${DateTime.now().millisecondsSinceEpoch}',
        qrCodeSvg: '<svg></svg>',
        isActive: true,
        createdAt: DateTime.now().toIso8601String(),
      ));
    }

    final endpoint = effectiveShopId == 'me'
        ? '$defaultBaseUrl/api/v1/shops/me/registration-qr/rotate'
        : '$defaultBaseUrl/api/v1/shops/$effectiveShopId/registration-qr/rotate';

    final url = Uri.parse(endpoint);
    try {
      final response = await _client.post(
        url,
        headers: buildHeaders(authToken: authToken),
      ).timeout(const Duration(seconds: 10));

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        return ApiResult.success(ShopRegistrationQrData.fromJson(data));
      } else {
        return ApiResult.failure(_extractErrorMessage(response));
      }
    } catch (e) {
      return ApiResult.failure('Failed to rotate QR: $e', isNetworkError: true);
    }
  }

  /// Revokes the active registration QR code for a shop.
  Future<ApiResult<bool>> revokeShopRegistrationQr(
    String? shopId, {
    required String authToken,
  }) async {
    if (mockInstance != null) {
      return mockInstance!.revokeShopRegistrationQr(shopId, authToken: authToken);
    }
    final effectiveShopId = (shopId == null || shopId.trim().isEmpty || shopId == 'me') ? 'me' : shopId.trim();

    if (isTestEnvironment && !enableLiveHttpInTests) {
      return ApiResult.success(true);
    }

    final endpoint = effectiveShopId == 'me'
        ? '$defaultBaseUrl/api/v1/shops/me/registration-qr/revoke'
        : '$defaultBaseUrl/api/v1/shops/$effectiveShopId/registration-qr/revoke';

    final url = Uri.parse(endpoint);
    try {
      final response = await _client.post(
        url,
        headers: buildHeaders(authToken: authToken),
      ).timeout(const Duration(seconds: 10));

      if (response.statusCode == 200) {
        return ApiResult.success(true);
      } else {
        return ApiResult.failure(_extractErrorMessage(response));
      }
    } catch (e) {
      return ApiResult.failure('Failed to revoke QR: $e', isNetworkError: true);
    }
  }

  /// Public shop lookup by QR token (unauthenticated, rate limited).
  Future<ApiResult<PublicShopInfo>> lookupPublicShop(String rawTokenOrUrl) async {
    if (mockInstance != null) {
      return mockInstance!.lookupPublicShop(rawTokenOrUrl);
    }
    // Extract token if user passed full URL
    final token = rawTokenOrUrl.trim().split('/').last.trim();
    if (token.isEmpty) {
      return ApiResult.failure('Invalid QR code or token');
    }

    if (isTestEnvironment && !enableLiveHttpInTests) {
      return ApiResult.success(PublicShopInfo(
        shopId: 'demo-shop-uuid',
        shopName: 'Chandra Kirana & Provisions',
        shopAddress: 'Shop #4, Market Road, Bengaluru',
        token: token,
      ));
    }

    final url = Uri.parse('$defaultBaseUrl/api/v1/public/shops/join/$token');
    try {
      final response = await _client.get(
        url,
        headers: buildHeaders(),
      ).timeout(const Duration(seconds: 10));

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        return ApiResult.success(PublicShopInfo.fromJson(data, token));
      } else {
        return ApiResult.failure(_extractErrorMessage(response));
      }
    } catch (e) {
      return ApiResult.failure('Failed to lookup shop: $e', isNetworkError: true);
    }
  }

  /// Customer explicitly joins a shop using a verified token.
  Future<ApiResult<Map<String, dynamic>>> joinShop({
    required String shopId,
    required String token,
    required String authToken,
  }) async {
    if (mockInstance != null) {
      return mockInstance!.joinShop(shopId: shopId, token: token, authToken: authToken);
    }
    if (isTestEnvironment && !enableLiveHttpInTests) {
      return ApiResult.success({
        'status': 'joined',
        'shop_id': shopId,
        'shop_name': 'Demo Store',
        'message': 'Successfully joined shop'
      });
    }

    final url = Uri.parse('$defaultBaseUrl/api/v1/shops/$shopId/join');
    try {
      final response = await _client.post(
        url,
        headers: buildHeaders(authToken: authToken),
        body: jsonEncode({'token': token.trim()}),
      ).timeout(const Duration(seconds: 10));

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        return ApiResult.success(data);
      } else {
        return ApiResult.failure(_extractErrorMessage(response));
      }
    } catch (e) {
      return ApiResult.failure('Failed to join shop: $e', isNetworkError: true);
    }
  }

  /// Retrieves all shops joined by the authenticated customer.
  Future<ApiResult<List<CustomerJoinedShop>>> getCustomerJoinedShops({
    required String authToken,
  }) async {
    if (mockInstance != null) {
      return mockInstance!.getCustomerJoinedShops(authToken: authToken);
    }
    if (isTestEnvironment && !enableLiveHttpInTests) {
      return ApiResult.success([
        CustomerJoinedShop(
          shopId: 'demo-shop-1',
          shopName: 'Chandra Kirana & Provisions',
          shopAddress: 'Shop #4, Market Road, Bengaluru',
          joinedAt: DateTime.now().toIso8601String(),
          status: 'ACTIVE',
        )
      ]);
    }

    final url = Uri.parse('$defaultBaseUrl/api/v1/customer/shops');
    try {
      final response = await _client.get(
        url,
        headers: buildHeaders(authToken: authToken),
      ).timeout(const Duration(seconds: 10));

      if (response.statusCode == 200) {
        final list = jsonDecode(response.body) as List<dynamic>;
        final shops = list.map((item) => CustomerJoinedShop.fromJson(item as Map<String, dynamic>)).toList();
        return ApiResult.success(shops);
      } else {
        return ApiResult.failure(_extractErrorMessage(response));
      }
    } catch (e) {
      return ApiResult.failure('Failed to fetch joined shops: $e', isNetworkError: true);
    }
  }

  /// Retrieves all registered customers for a shopkeeper's shop.
  /// If shopId is null, empty or 'me', resolves the authenticated user's shop automatically.
  Future<ApiResult<List<ShopCustomerItem>>> getShopCustomers(
    String? shopId, {
    required String authToken,
  }) async {
    if (mockShopCustomersResult != null) {
      return mockShopCustomersResult!;
    }
    if (mockInstance != null) {
      return mockInstance!.getShopCustomers(shopId, authToken: authToken);
    }
    final effectiveShopId = (shopId == null || shopId.trim().isEmpty || shopId == 'me') ? 'me' : shopId.trim();

    if (isTestEnvironment && !enableLiveHttpInTests) {
      return ApiResult.success([
        ShopCustomerItem(
          customerId: 'cust-1',
          fullName: 'Ananya Sharma',
          phone: '+919876543210',
          address: 'Main Street',
          joinedAt: DateTime.now().toIso8601String(),
          status: 'ACTIVE',
        )
      ]);
    }

    final endpoint = effectiveShopId == 'me'
        ? '$defaultBaseUrl/api/v1/shops/me/customers'
        : '$defaultBaseUrl/api/v1/shops/$effectiveShopId/customers';

    final url = Uri.parse(endpoint);
    try {
      final response = await _client.get(
        url,
        headers: buildHeaders(authToken: authToken),
      ).timeout(const Duration(seconds: 10));

      if (response.statusCode == 200) {
        final list = jsonDecode(response.body) as List<dynamic>;
        final customers = list.map((item) => ShopCustomerItem.fromJson(item as Map<String, dynamic>)).toList();
        return ApiResult.success(customers);
      } else {
        return ApiResult.failure(_extractErrorMessage(response));
      }
    } catch (e) {
      return ApiResult.failure('Failed to fetch shop customers: $e', isNetworkError: true);
    }
  }

  /// Retrieves static UPI payment QR details for a connected customer.
  Future<ApiResult<CustomerShopPaymentQr>> getCustomerShopPaymentQr(
    String shopId, {
    required String authToken,
  }) async {
    if (isTestEnvironment && !enableLiveHttpInTests) {
      return ApiResult.success(
        CustomerShopPaymentQr(
          shopId: shopId,
          shopName: 'Sample Merchant',
          upiId: 'merchant@upi',
          hasPaymentQr: true,
          paymentQrUrl: '/api/v1/customer/shops/$shopId/payment-qr/image',
          upiProvider: 'BHIM/UPI',
          disclaimer:
              'Scan or pay using any UPI app (GPay, PhonePe, Paytm, BHIM). Qbox does not hold or process customer funds; payments are made directly to the merchant.',
        ),
      );
    }

    final url = Uri.parse('$defaultBaseUrl/api/v1/customer/shops/$shopId/payment-qr');
    try {
      final response = await _client.get(
        url,
        headers: buildHeaders(authToken: authToken),
      ).timeout(const Duration(seconds: 10));

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        return ApiResult.success(CustomerShopPaymentQr.fromJson(data));
      } else {
        return ApiResult.failure(_extractErrorMessage(response));
      }
    } catch (e) {
      return ApiResult.failure('Failed to fetch payment QR: $e', isNetworkError: true);
    }
  }

  /// Retrieves active static payment QR metadata for a shopkeeper.
  Future<ApiResult<ShopPaymentQrMeta?>> getShopPaymentQrMeta(
    String? shopId, {
    required String authToken,
  }) async {
    final effectiveShopId = (shopId == null || shopId.trim().isEmpty || shopId == 'me') ? 'me' : shopId.trim();
    if (isTestEnvironment && !enableLiveHttpInTests) {
      return ApiResult.success(
        ShopPaymentQrMeta(
          id: 'mock-pqr-id',
          shopId: effectiveShopId,
          originalFilename: 'store_payment_qr.png',
          contentType: 'image/png',
          fileSizeBytes: 245000,
          upiProvider: 'PHONEPE',
          imageUrl: '/api/v1/shops/$effectiveShopId/payment-qr/image',
          isActive: true,
          createdAt: DateTime.now().toIso8601String(),
          updatedAt: DateTime.now().toIso8601String(),
        ),
      );
    }

    final url = Uri.parse('$defaultBaseUrl/api/v1/shops/$effectiveShopId/payment-qr');
    try {
      final response = await _client.get(
        url,
        headers: buildHeaders(authToken: authToken),
      ).timeout(const Duration(seconds: 10));

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        return ApiResult.success(ShopPaymentQrMeta.fromJson(data));
      } else if (response.statusCode == 404) {
        return ApiResult.success(null);
      } else {
        return ApiResult.failure(_extractErrorMessage(response));
      }
    } catch (e) {
      return ApiResult.failure('Failed to fetch payment QR metadata: $e', isNetworkError: true);
    }
  }

  /// Updates or replaces the shopkeeper's static payment QR image.
  Future<ApiResult<ShopPaymentQrMeta>> updateShopPaymentQr(
    String? shopId, {
    required String authToken,
    String? filePath,
    List<int>? fileBytes,
    String? fileName,
  }) async {
    final effectiveShopId = (shopId == null || shopId.trim().isEmpty || shopId == 'me') ? 'me' : shopId.trim();
    if (isTestEnvironment && !enableLiveHttpInTests) {
      return ApiResult.success(
        ShopPaymentQrMeta(
          id: 'mock-pqr-id-updated',
          shopId: effectiveShopId,
          originalFilename: fileName ?? 'updated_qr.png',
          contentType: 'image/png',
          fileSizeBytes: fileBytes?.length ?? 128000,
          upiProvider: 'GOOGLE_PAY',
          imageUrl: '/api/v1/shops/$effectiveShopId/payment-qr/image',
          isActive: true,
          createdAt: DateTime.now().toIso8601String(),
          updatedAt: DateTime.now().toIso8601String(),
        ),
      );
    }

    final url = Uri.parse('$defaultBaseUrl/api/v1/shops/$effectiveShopId/payment-qr');
    try {
      final request = http.MultipartRequest('PUT', url);
      request.headers.addAll(buildHeaders(authToken: authToken, json: false));

      if (filePath != null) {
        request.files.add(await http.MultipartFile.fromPath('payment_qr_image', filePath));
      } else if (fileBytes != null) {
        request.files.add(http.MultipartFile.fromBytes(
          'payment_qr_image',
          fileBytes,
          filename: fileName ?? 'payment_qr.png',
        ));
      } else {
        return ApiResult.failure('No image file provided for upload.');
      }

      final streamed = await _client.send(request).timeout(const Duration(seconds: 15));
      final response = await http.Response.fromStream(streamed);

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        return ApiResult.success(ShopPaymentQrMeta.fromJson(data));
      } else {
        return ApiResult.failure(_extractErrorMessage(response));
      }
    } catch (e) {
      return ApiResult.failure('Failed to update payment QR: $e', isNetworkError: true);
    }
  }

  /// Deactivates / removes the shopkeeper's static payment QR image.
  Future<ApiResult<bool>> deleteShopPaymentQr(
    String? shopId, {
    required String authToken,
  }) async {
    final effectiveShopId = (shopId == null || shopId.trim().isEmpty || shopId == 'me') ? 'me' : shopId.trim();
    if (isTestEnvironment && !enableLiveHttpInTests) {
      return ApiResult.success(true);
    }

    final url = Uri.parse('$defaultBaseUrl/api/v1/shops/$effectiveShopId/payment-qr');
    try {
      final response = await _client.delete(
        url,
        headers: buildHeaders(authToken: authToken),
      ).timeout(const Duration(seconds: 10));

      if (response.statusCode == 200) {
        return ApiResult.success(true);
      } else {
        return ApiResult.failure(_extractErrorMessage(response));
      }
    } catch (e) {
      return ApiResult.failure('Failed to remove payment QR: $e', isNetworkError: true);
    }
  }

  /// Downloads payment QR image bytes securely with Authorization header.
  Future<ApiResult<Uint8List>> downloadPaymentQrImage({
    required String url,
    required String authToken,
  }) async {
    final uri = url.startsWith('http') ? Uri.parse(url) : Uri.parse('$defaultBaseUrl$url');
    try {
      final response = await _client.get(
        uri,
        headers: buildHeaders(authToken: authToken, json: false),
      ).timeout(const Duration(seconds: 10));

      if (response.statusCode == 200) {
        return ApiResult.success(response.bodyBytes);
      } else {
        return ApiResult.failure('Failed to download QR image (HTTP ${response.statusCode})');
      }
    } catch (e) {
      return ApiResult.failure('Download failed: $e', isNetworkError: true);
    }
  }

  /// Parses error message from FastAPI response body.
  static String _extractErrorMessage(http.Response response) {
    try {
      final json = jsonDecode(response.body);
      if (json is Map<String, dynamic>) {
        if (json.containsKey('detail')) {
          final detail = json['detail'];
          if (detail is String) return detail;
          if (detail is List && detail.isNotEmpty) {
            final first = detail.first;
            if (first is Map && first.containsKey('msg')) {
              return first['msg'].toString();
            }
            return detail.toString();
          }
        }
      }
    } catch (_) {}
    return 'Server returned status code ${response.statusCode}';
  }
}
