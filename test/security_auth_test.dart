import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:qbox_shopkeeper_demo/config/app_config.dart';
import 'package:qbox_shopkeeper_demo/main.dart';
import 'package:qbox_shopkeeper_demo/models/profiles.dart';
import 'package:qbox_shopkeeper_demo/screens/customer_home_screen.dart';
import 'package:qbox_shopkeeper_demo/screens/customer_login_screen.dart';
import 'package:qbox_shopkeeper_demo/screens/customer_signup_screen.dart';
import 'package:qbox_shopkeeper_demo/screens/scan_shop_qr_screen.dart';
import 'package:qbox_shopkeeper_demo/screens/shop_qr_management_screen.dart';
import 'package:qbox_shopkeeper_demo/services/api_service.dart';
import 'package:qbox_shopkeeper_demo/services/deep_link_service.dart';
import 'package:qbox_shopkeeper_demo/services/token_storage_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('TokenStorageService Unit Tests', () {
    final storage = TokenStorageService();

    setUp(() async {
      await storage.clearAll();
    });

    test('stores, retrieves, and wipes JWT access and refresh tokens', () async {
      expect(await storage.getAccessToken(), isNull);
      expect(await storage.getRefreshToken(), isNull);

      await storage.saveTokens(
        accessToken: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test-access',
        refreshToken: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test-refresh',
      );

      expect(await storage.getAccessToken(), 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test-access');
      expect(await storage.getRefreshToken(), 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test-refresh');

      await storage.clearAll();
      expect(await storage.getAccessToken(), isNull);
      expect(await storage.getRefreshToken(), isNull);
    });

    test('stores and retrieves ShopkeeperProfile and active role', () async {
      await storage.saveTokens(
        accessToken: 'valid-shopkeeper-token',
        refreshToken: 'valid-shopkeeper-refresh',
      );
      await storage.saveActiveRole('shopkeeper');

      final profile = ShopkeeperProfile(
        fullName: 'Ramesh Chandra',
        shopName: 'Chandra Store',
        shopAddress: 'Bengaluru Market',
        phone: '9876543210',
        userId: 'u-123',
        shopId: 's-456',
      );

      await storage.saveShopkeeperProfile(profile);

      expect(await storage.getActiveRole(), 'shopkeeper');
      final retrieved = await storage.getShopkeeperProfile();
      expect(retrieved, isNotNull);
      expect(retrieved!.fullName, 'Ramesh Chandra');
      expect(retrieved.shopName, 'Chandra Store');
      expect(retrieved.shopAddress, 'Bengaluru Market');
      expect(retrieved.phone, '9876543210');
      expect(retrieved.userId, 'u-123');
      expect(retrieved.shopId, 's-456');
      expect(retrieved.accessToken, 'valid-shopkeeper-token');

      await storage.clearAll();
      expect(await storage.getActiveRole(), isNull);
      expect(await storage.getShopkeeperProfile(), isNull);
    });

    test('stores and retrieves RegisteredCustomer profile', () async {
      await storage.saveTokens(
        accessToken: 'valid-customer-token',
        refreshToken: 'valid-customer-refresh',
      );
      await storage.saveActiveRole('customer');

      final customer = RegisteredCustomer(
        fullName: 'Sravani Customer',
        phone: '9123456780',
        address: 'Indiranagar, Bengaluru',
        userId: 'cust-uuid-1',
      );

      await storage.saveCustomerProfile(customer);

      expect(await storage.getActiveRole(), 'customer');
      final retrieved = await storage.getCustomerProfile();
      expect(retrieved, isNotNull);
      expect(retrieved!.fullName, 'Sravani Customer');
      expect(retrieved.phone, '9123456780');
      expect(retrieved.address, 'Indiranagar, Bengaluru');
      expect(retrieved.userId, 'cust-uuid-1');
      expect(retrieved.accessToken, 'valid-customer-token');
    });

    test('production environment fails safely without in-memory fallback when hardware storage fails', () async {
      TokenStorageService.testEnvironmentOverride = false;
      addTearDown(() {
        TokenStorageService.testEnvironmentOverride = null;
      });

      final failingStorage = _FailingSecureStorage();
      final prodService = TokenStorageService(storage: failingStorage);

      // Verify that saveTokens throws SecureStorageException in production simulation
      expect(
        () => prodService.saveTokens(
          accessToken: 'prod-secret-access',
          refreshToken: 'prod-secret-refresh',
        ),
        throwsA(isA<SecureStorageException>()),
      );

      // Verify that the in-memory test store was NOT written to and remains empty
      expect(TokenStorageService.testMemoryStore['qbox_secure_access_token'], isNull);
      expect(TokenStorageService.testMemoryStore['qbox_secure_refresh_token'], isNull);

      // Verify that read fails safely by returning null rather than falling back to memory
      expect(await prodService.getAccessToken(), isNull);
      expect(await prodService.getRefreshToken(), isNull);

      // Verify profile write throws SecureStorageException
      expect(
        () => prodService.saveShopkeeperProfile(
          ShopkeeperProfile(
            fullName: 'Ramesh',
            shopName: 'Store',
            shopAddress: 'Road',
            phone: '9876543210',
          ),
        ),
        throwsA(isA<SecureStorageException>()),
      );
      expect(TokenStorageService.testMemoryStore['qbox_secure_shopkeeper_profile'], isNull);
    });

    test('automated test environment strictly uses in-memory store for headless test compatibility', () async {
      TokenStorageService.testEnvironmentOverride = true;
      addTearDown(() {
        TokenStorageService.testEnvironmentOverride = null;
      });

      final testService = TokenStorageService();
      await testService.saveTokens(accessToken: 'test-token', refreshToken: 'test-refresh');

      expect(TokenStorageService.testMemoryStore['qbox_secure_access_token'], 'test-token');
      expect(await testService.getAccessToken(), 'test-token');
    });
  });

  group('QboxStore Authentication State Tests', () {
    final storage = TokenStorageService();

    setUp(() async {
      await storage.clearAll();
    });

    test('correctly distinguishes demo mode from server-authenticated session', () {
      final store = QboxStore();

      // Initial state: not authenticated
      expect(store.isAuthenticated, isFalse);
      expect(store.hasServerAuth, isFalse);
      expect(store.isDemoSession, isFalse);

      // Demo login: activeSessionRole set but NO accessToken
      store.setShopkeeper(
        ShopkeeperProfile(
          fullName: 'Demo Shopkeeper',
          shopName: 'Demo Store',
          shopAddress: 'MG Road',
          phone: '9876543210',
        ),
        token: null,
        refresh: null,
      );

      expect(store.isAuthenticated, isTrue); // Legacy compatibility
      expect(store.hasServerAuth, isFalse); // No genuine server token
      expect(store.isDemoSession, isTrue); // Explicitly recognized as demo

      // Server-authenticated login: with real tokens
      store.setShopkeeper(
        ShopkeeperProfile(
          fullName: 'Live Shopkeeper',
          shopName: 'Live Store',
          shopAddress: 'Commercial Street',
          phone: '9876543210',
        ),
        token: 'real-server-jwt-access',
        refresh: 'real-server-jwt-refresh',
      );

      expect(store.isAuthenticated, isTrue);
      expect(store.hasServerAuth, isTrue);
      expect(store.isDemoSession, isFalse);
    });

    test('logout clears in-memory state and hardware secure storage', () async {
      final store = QboxStore();

      store.setShopkeeper(
        ShopkeeperProfile(
          fullName: 'Live Shopkeeper',
          shopName: 'Live Store',
          shopAddress: 'Commercial Street',
          phone: '9876543210',
        ),
        token: 'real-server-jwt-access',
        refresh: 'real-server-jwt-refresh',
      );

      expect(store.hasServerAuth, isTrue);

      final mockApi = _RecordingLogoutApiService();
      await store.logoutAsync(apiService: mockApi);

      expect(store.isAuthenticated, isFalse);
      expect(store.hasServerAuth, isFalse);
      expect(store.accessToken, isNull);
      expect(store.refreshToken, isNull);
      expect(store.activeSessionRole, isNull);

      // Verify secure storage was wiped
      expect(await storage.getAccessToken(), isNull);
      expect(await storage.getRefreshToken(), isNull);

      // Verify server-side invalidation API was called
      expect(mockApi.logoutCalled, isTrue);
      expect(mockApi.lastAuthToken, 'real-server-jwt-access');
      expect(mockApi.lastRefreshToken, 'real-server-jwt-refresh');
    });

    test('initializeFromStorage restores authenticated session from hardware storage', () async {
      await storage.saveTokens(
        accessToken: 'persisted-access-jwt',
        refreshToken: 'persisted-refresh-jwt',
      );
      await storage.saveActiveRole('shopkeeper');
      await storage.saveShopkeeperProfile(
        ShopkeeperProfile(
          fullName: 'Persisted Owner',
          shopName: 'Persisted Shop',
          shopAddress: 'Brigade Road',
          phone: '9876543210',
          shopId: 'persisted-shop-id',
        ),
      );

      final store = QboxStore();
      expect(store.hasServerAuth, isFalse);

      await store.initializeFromStorage();

      expect(store.hasServerAuth, isTrue);
      expect(store.isDemoSession, isFalse);
      expect(store.accessToken, 'persisted-access-jwt');
      expect(store.refreshToken, 'persisted-refresh-jwt');
      expect(store.activeSessionRole, 'shopkeeper');
      expect(store.shopkeeperProfile, isNotNull);
      expect(store.shopkeeperProfile!.shopName, 'Persisted Shop');
    });
  });

  group('Demo Mode Protection on Protected Screens Tests', () {
    testWidgets('ShopQrManagementScreen blocks API calls when session is in Demo Mode', (tester) async {
      tester.view.physicalSize = const Size(800, 1600);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final store = QboxStore();
      // Set offline demo shopkeeper without tokens
      store.setShopkeeper(
        ShopkeeperProfile(
          fullName: 'Demo Shopkeeper',
          shopName: 'Demo Store',
          shopAddress: 'MG Road',
          phone: '9876543210',
        ),
        token: null,
        refresh: null,
      );

      final spyApi = _SpyProtectedApiService();

      await tester.pumpWidget(
        MaterialApp(
          home: ShopQrManagementScreen(store: store, apiService: spyApi),
        ),
      );
      await tester.pumpAndSettle();

      // Verify NO protected backend API call was made
      expect(spyApi.getQrCalled, isFalse);

      // Verify friendly Offline Demo message and log in action
      expect(find.textContaining('Offline Demo Mode'), findsOneWidget);
      expect(find.text('Log In as Shopkeeper'), findsOneWidget);
    });

    testWidgets('ScanShopQrScreen requires customer authentication to join a shop', (tester) async {
      tester.view.physicalSize = const Size(800, 1600);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final store = QboxStore();
      // In demo mode without server tokens
      store.setCustomer(
        RegisteredCustomer(
          fullName: 'Demo Customer',
          phone: '9123456780',
          address: 'Bengaluru',
        ),
        token: null,
      );

      await tester.pumpWidget(
        MaterialApp(
          home: ScanShopQrScreen(store: store),
        ),
      );
      await tester.pumpAndSettle();

      // The Join Shop via QR screen is visible
      expect(find.text('Join Shop via QR'), findsOneWidget);
    });
  });

  group('Development Environment Configuration & Device Routing Tests', () {
    tearDown(() {
      AppConfig.reset();
    });

    test('AppConfig resolves to Android emulator 10.0.2.2:8000 when emulator environment is active', () {
      AppConfig.setEnvironment(AppEnvironment.emulator);
      expect(AppConfig.activeEnvironment, AppEnvironment.emulator);
      expect(AppConfig.baseUrl, 'http://10.0.2.2:8000');
      expect(ApiService.defaultBaseUrl, 'http://10.0.2.2:8000');
      expect(AppConfig.environmentLabel, contains('10.0.2.2:8000'));
    });

    test('AppConfig resolves to physical device 192.168.1.5:8000 when physicalDevice is active', () {
      AppConfig.setEnvironment(AppEnvironment.physicalDevice);
      expect(AppConfig.activeEnvironment, AppEnvironment.physicalDevice);
      expect(AppConfig.baseUrl, 'http://192.168.1.5:8000');
      expect(ApiService.defaultBaseUrl, 'http://192.168.1.5:8000');
      expect(AppConfig.environmentLabel, contains('192.168.1.5:8000'));
    });

    test('AppConfig production environment strictly resolves to https://api.qbox.app without dev IP leakage', () {
      AppConfig.setEnvironment(AppEnvironment.production);
      expect(AppConfig.activeEnvironment, AppEnvironment.production);
      expect(AppConfig.baseUrl, 'https://api.qbox.app');
      expect(AppConfig.baseUrl, isNot(contains('192.168.1.5')));
      expect(AppConfig.baseUrl, isNot(contains('10.0.2.2')));
    });

    test('ApiService.buildHeaders attaches X-Client-Device header matching active environment', () {
      AppConfig.setEnvironment(AppEnvironment.physicalDevice);
      final physHeaders = ApiService.buildHeaders(authToken: 'sample-jwt');
      expect(physHeaders['X-Client-Device'], 'physical');
      expect(physHeaders['Authorization'], 'Bearer sample-jwt');
      expect(physHeaders['Content-Type'], 'application/json');

      AppConfig.setEnvironment(AppEnvironment.emulator);
      final emuHeaders = ApiService.buildHeaders();
      expect(emuHeaders['X-Client-Device'], 'emulator');
      expect(emuHeaders['Authorization'], isNull);
    });

    test('AppConfig runtime custom URL override takes precedence and resets cleanly', () {
      AppConfig.setBaseUrl('http://192.168.1.100:9000');
      expect(AppConfig.baseUrl, 'http://192.168.1.100:9000');
      expect(ApiService.defaultBaseUrl, 'http://192.168.1.100:9000');

      AppConfig.reset();
      expect(AppConfig.baseUrl, isNot('http://192.168.1.100:9000'));
    });
  });

  group('Android Deep Linking & Customer Onboarding Routing Tests', () {
    test('extractToken handles custom Android scheme qbox://join/{token}', () {
      expect(
        DeepLinkService.extractToken('qbox://join/sec-token-12345'),
        'sec-token-12345',
      );
    });

    test('extractToken handles Android Intent URIs from mobile browsers', () {
      final intentUri =
          'intent://join/token-xyz-789#Intent;scheme=qbox;package=com.example.qbox_shopkeeper_demo;end';
      expect(DeepLinkService.extractToken(intentUri), 'token-xyz-789');
    });

    test('extractToken handles HTTP / HTTPS LAN and production URLs', () {
      expect(
        DeepLinkService.extractToken('http://192.168.1.5:8000/join/lan-token-99'),
        'lan-token-99',
      );
      expect(
        DeepLinkService.extractToken('https://qbox.app/join/prod-token-42/'),
        'prod-token-42',
      );
      expect(
        DeepLinkService.extractToken('http://10.0.2.2:8000/join?token=param-token-88'),
        'param-token-88',
      );
    });

    test('extractToken safely rejects malformed or missing tokens', () {
      expect(DeepLinkService.extractToken(null), isNull);
      expect(DeepLinkService.extractToken(''), isNull);
      expect(DeepLinkService.extractToken('   '), isNull);
      expect(DeepLinkService.extractToken('qbox://join'), isNull);
      expect(DeepLinkService.extractToken('http://192.168.1.5:8000/other/path'), isNull);
    });

    test('DeepLinkService correctly handles platform channel invocation', () async {
      String? receivedToken;
      const mockChannel = MethodChannel('com.example.qbox/deeplink');

      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
        mockChannel,
        (call) async {
          if (call.method == 'getInitialDeepLink') {
            return 'qbox://join/cold-start-token-001';
          }
          return null;
        },
      );

      final service = DeepLinkService(channel: mockChannel);
      await service.initialize(onTokenReceived: (t) {
        receivedToken = t;
      });

      expect(receivedToken, 'cold-start-token-001');

      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
        mockChannel,
        null,
      );
    });
  });

  group('Customer Onboarding & Single-Scan Invitation Flow Tests', () {
    final storage = TokenStorageService();

    setUp(() async {
      await storage.clearAll();
    });

    test('TokenStorageService securely saves, reads, and clears pending shop registration token', () async {
      expect(await storage.getPendingShopToken(), isNull);
      await storage.savePendingShopToken('pending-qr-token-xyz');
      expect(await storage.getPendingShopToken(), 'pending-qr-token-xyz');
      await storage.clearPendingShopToken();
      expect(await storage.getPendingShopToken(), isNull);
    });

    test('QboxStore saves, restores, and clears pendingShopToken', () async {
      final store = QboxStore();
      expect(store.pendingShopToken, isNull);

      await store.setPendingShopToken('token-abc-999');
      expect(store.pendingShopToken, 'token-abc-999');
      expect(await storage.getPendingShopToken(), 'token-abc-999');

      // Restoring from storage
      final store2 = QboxStore();
      await store2.initializeFromStorage();
      expect(store2.pendingShopToken, 'token-abc-999');

      await store.clearPendingShopToken();
      expect(store.pendingShopToken, isNull);
      expect(await storage.getPendingShopToken(), isNull);
    });

    testWidgets('CustomerSignUpScreen preserves pendingShopToken and automatically continues to ScanShopQrScreen', (tester) async {
      tester.view.physicalSize = const Size(800, 1600);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final store = QboxStore();
      await store.setPendingShopToken('invitation-token-555');

      ApiService.mockCustomerRegisterResult = ApiResult.success(
        RegisteredCustomer(
          fullName: 'Rahul Dravid',
          phone: '+919876543210',
          address: 'Chinnaswamy, Bengaluru',
          userId: 'test-user-id-555',
          accessToken: 'mock-jwt-rahul',
          refreshToken: 'mock-refresh-rahul',
        ),
      );
      addTearDown(ApiService.resetTestMocks);

      await tester.pumpWidget(MaterialApp(
        home: CustomerSignUpScreen(store: store),
      ));
      await tester.pumpAndSettle();

      // Enter registration details (strictly 3 mandatory fields: Name, Phone, Address)
      await tester.enterText(find.byType(TextFormField).at(0), 'Rahul Dravid');
      await tester.enterText(find.byType(TextFormField).at(1), '9876543210');
      await tester.enterText(find.byType(TextFormField).at(2), 'Chinnaswamy, Bengaluru');

      // Submit registration
      await tester.tap(find.widgetWithText(FilledButton, 'Register as Customer'));
      await tester.pumpAndSettle();

      // Customer is now authenticated AND lands on ScanShopQrScreen without having to scan again!
      expect(find.byType(ScanShopQrScreen), findsOneWidget);
      expect(store.isAuthenticated, isTrue);
      expect(store.activeSessionRole, 'customer');
      expect(store.pendingShopToken, 'invitation-token-555');
    });

    testWidgets('CustomerLoginScreen preserves pendingShopToken and automatically continues to ScanShopQrScreen', (tester) async {
      tester.view.physicalSize = const Size(800, 1600);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final store = QboxStore();
      await store.setPendingShopToken('invitation-token-777');

      ApiService.mockLoginResult = ApiResult.success(
        LoginResultData(
          accessToken: 'test-customer-token',
          refreshToken: 'test-customer-refresh',
          roles: ['CUSTOMER'],
          profile: ShopkeeperProfile(
            fullName: 'Rahul Dravid',
            shopName: '',
            shopAddress: 'Bengaluru',
            phone: '+919876543210',
            userId: 'cust-uuid-777',
          ),
        ),
      );
      addTearDown(ApiService.resetTestMocks);

      await tester.pumpWidget(MaterialApp(
        home: CustomerLoginScreen(store: store),
      ));
      await tester.pumpAndSettle();

      // Enter mobile number
      await tester.enterText(find.byType(TextFormField).first, '9876543210');

      // Submit login
      await tester.tap(find.widgetWithText(FilledButton, 'Login to Customer Portal'));
      await tester.pumpAndSettle();

      // Automatically continues pending invitation on ScanShopQrScreen
      expect(find.byType(ScanShopQrScreen), findsOneWidget);
      expect(store.isAuthenticated, isTrue);
      expect(store.activeSessionRole, 'customer');
      expect(store.pendingShopToken, 'invitation-token-777');
    });

    testWidgets('ScanShopQrScreen displays explicit confirmation and Cancel button clears token without joining', (tester) async {
      tester.view.physicalSize = const Size(800, 1600);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final store = QboxStore();
      final customer = RegisteredCustomer(
        fullName: 'Asha Bhosle',
        phone: '9876543210',
        address: 'Bandra, Mumbai',
        accessToken: 'mock-jwt-asha',
      );
      store.setCustomer(customer);
      await store.setPendingShopToken('cancel-test-token');

      await tester.pumpWidget(MaterialApp(
        home: ScanShopQrScreen(store: store, initialToken: 'cancel-test-token'),
      ));
      await tester.pumpAndSettle();

      // Displays verified merchant details and explicit confirmation message
      expect(find.text('VERIFIED QBOX MERCHANT'), findsOneWidget);
      expect(find.text('Chandra Kirana & Provisions'), findsOneWidget);
      expect(find.textContaining('Do you want to connect your Qbox account with Chandra Kirana & Provisions?'), findsOneWidget);
      expect(find.text('Join Shop'), findsOneWidget);
      expect(find.text('Cancel'), findsOneWidget);

      // Tap Cancel
      await tester.tap(find.text('Cancel'));
      await tester.pumpAndSettle();

      // Verifies token is cleared from store and storage, and user lands on CustomerHomeScreen without joining
      expect(store.pendingShopToken, isNull);
      expect(await storage.getPendingShopToken(), isNull);
      expect(find.byType(CustomerHomeScreen), findsOneWidget);
    });

    testWidgets('ScanShopQrScreen handles invalid tokens cleanly with error banner', (tester) async {
      tester.view.physicalSize = const Size(800, 1600);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final store = QboxStore();

      await tester.pumpWidget(MaterialApp(
        home: ScanShopQrScreen(store: store),
      ));
      await tester.pumpAndSettle();

      // Submit empty or invalid code
      await tester.tap(find.widgetWithText(FilledButton, 'Verify Shop Code'));
      await tester.pumpAndSettle();

      expect(find.text('Please enter or scan a valid QR registration link or token'), findsOneWidget);
      expect(find.text('Join Shop'), findsNothing);
    });
  });
}

class _RecordingLogoutApiService extends ApiService {
  bool logoutCalled = false;
  String? lastAuthToken;
  String? lastRefreshToken;

  @override
  Future<ApiResult<bool>> logout({
    required String authToken,
    String? refreshToken,
    bool allSessions = false,
  }) async {
    logoutCalled = true;
    lastAuthToken = authToken;
    lastRefreshToken = refreshToken;
    return ApiResult.success(true);
  }
}

class _SpyProtectedApiService extends ApiService {
  bool getQrCalled = false;

  @override
  Future<ApiResult<ShopRegistrationQrData>> getShopRegistrationQr(
    String? shopId, {
    required String authToken,
  }) async {
    getQrCalled = true;
    return ApiResult.failure('Should not be called in demo mode');
  }
}

class _FailingSecureStorage extends Fake implements FlutterSecureStorage {
  @override
  Future<void> write({
    required String key,
    required String? value,
    AppleOptions? iOptions,
    AndroidOptions? aOptions,
    LinuxOptions? lOptions,
    WebOptions? webOptions,
    AppleOptions? mOptions,
    WindowsOptions? wOptions,
  }) async {
    throw Exception('Keystore unavailable: hardware keymaster error');
  }

  @override
  Future<String?> read({
    required String key,
    AppleOptions? iOptions,
    AndroidOptions? aOptions,
    LinuxOptions? lOptions,
    WebOptions? webOptions,
    AppleOptions? mOptions,
    WindowsOptions? wOptions,
  }) async {
    throw Exception('Keystore decryption failed: authentication failed');
  }

  @override
  Future<void> deleteAll({
    AppleOptions? iOptions,
    AndroidOptions? aOptions,
    LinuxOptions? lOptions,
    WebOptions? webOptions,
    AppleOptions? mOptions,
    WindowsOptions? wOptions,
  }) async {
    throw Exception('Keystore wipe failed');
  }
}
