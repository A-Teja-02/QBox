import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image_picker/image_picker.dart';
import 'package:qbox_shopkeeper_demo/main.dart';
import 'package:qbox_shopkeeper_demo/models/profiles.dart';
import 'package:qbox_shopkeeper_demo/screens/customer_home_screen.dart';
import 'package:qbox_shopkeeper_demo/screens/customer_login_screen.dart';
import 'package:qbox_shopkeeper_demo/screens/customer_signup_screen.dart';
import 'package:qbox_shopkeeper_demo/screens/scan_shop_qr_screen.dart';
import 'package:qbox_shopkeeper_demo/screens/shop_qr_management_screen.dart';
import 'package:qbox_shopkeeper_demo/screens/shopkeeper_login_screen.dart';
import 'package:qbox_shopkeeper_demo/screens/shopkeeper_signup_screen.dart';
import 'package:qbox_shopkeeper_demo/screens/welcome_screen.dart';
import 'package:qbox_shopkeeper_demo/services/api_service.dart';
import 'package:qbox_shopkeeper_demo/utils/validators.dart';
import 'package:qbox_shopkeeper_demo/widgets/qr_preview_card.dart';

void main() {
  // 1. Preserve original passing test
  test('money formatting preserves paise', () {
    expect(money(10000), '₹100.00');
    expect(money(10050), '₹100.50');
    expect(money(75), '₹0.75');
    expect(money(125075), '₹1250.75');
  });

  group('Validators Unit Tests', () {
    test('validatePhone accepts valid Indian phone formats', () {
      expect(Validators.validatePhone('9876543210'), isNull);
      expect(Validators.validatePhone('+91 98765 43210'), isNull);
      expect(Validators.validatePhone('09876543210'), isNull);
      expect(Validators.validatePhone('919876543210'), isNull);
      expect(Validators.validatePhone('6123456789'), isNull);
      expect(Validators.validatePhone('7123456789'), isNull);
      expect(Validators.validatePhone('8123456789'), isNull);
    });

    test('validatePhone rejects invalid phone numbers', () {
      expect(Validators.validatePhone(''), isNotNull);
      expect(Validators.validatePhone(null), isNotNull);
      expect(Validators.validatePhone('12345'), isNotNull);
      expect(Validators.validatePhone('5123456789'), isNotNull);
      expect(Validators.validatePhone('abcdefghij'), isNotNull);
    });

    test('validateUpi handles optional and format checks correctly', () {
      expect(Validators.validateUpi(''), isNull);
      expect(Validators.validateUpi(null), isNull);
      expect(Validators.validateUpi('   '), isNull);

      expect(Validators.validateUpi('shopkeeper@upi'), isNull);
      expect(Validators.validateUpi('ramesh.kumar@okhdfcbank'), isNull);
      expect(Validators.validateUpi('9876543210@paytm'), isNull);

      expect(Validators.validateUpi('invalidupi'), isNotNull);
      expect(Validators.validateUpi('user@'), isNotNull);
      expect(Validators.validateUpi('@bank'), isNotNull);
    });

    test('validateRequired validates mandatory strings and lengths', () {
      expect(Validators.validateRequired('', 'Name'), isNotNull);
      expect(Validators.validateRequired(null, 'Name'), isNotNull);
      expect(Validators.validateRequired('A', 'Name', minLength: 2), isNotNull);
      expect(Validators.validateRequired('Al', 'Name', minLength: 2), isNull);
      expect(Validators.validateRequired('Valid text', 'Name'), isNull);
    });
  });

  group('Welcome Screen & Role Selection Widget Tests', () {
    testWidgets('renders brand title, tagline and two role cards', (tester) async {
      tester.view.physicalSize = const Size(800, 1400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final store = QboxStore();
      await tester.pumpWidget(
        MaterialApp(
          home: WelcomeScreen(store: store),
        ),
      );

      expect(find.text('Qbox'), findsOneWidget);
      expect(find.text('Your Shop. Your Business. Simplified.'), findsOneWidget);
      expect(find.text("I'm a Shopkeeper"), findsOneWidget);
      expect(find.text("I'm a Customer"), findsOneWidget);
      expect(find.text('Sign Up'), findsNWidgets(2));
      expect(find.text('Login'), findsNWidgets(2));
    });

    testWidgets('navigates to Shopkeeper Sign Up screen', (tester) async {
      tester.view.physicalSize = const Size(800, 1400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final store = QboxStore();
      await tester.pumpWidget(
        MaterialApp(
          home: WelcomeScreen(store: store),
        ),
      );

      await tester.tap(find.text('Sign Up').first);
      await tester.pumpAndSettle();

      expect(find.byType(ShopkeeperSignUpScreen), findsOneWidget);
      expect(find.text('Shopkeeper Registration'), findsOneWidget);
    });

    testWidgets('navigates to Shopkeeper Login screen', (tester) async {
      tester.view.physicalSize = const Size(800, 1400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final store = QboxStore();
      await tester.pumpWidget(
        MaterialApp(
          home: WelcomeScreen(store: store),
        ),
      );

      await tester.tap(find.text('Login').first);
      await tester.pumpAndSettle();

      expect(find.byType(ShopkeeperLoginScreen), findsOneWidget);
      expect(find.text('Shopkeeper Login'), findsOneWidget);
      expect(find.text('Welcome Back, Shopkeeper'), findsOneWidget);
    });

    testWidgets('navigates to Customer Sign Up screen', (tester) async {
      tester.view.physicalSize = const Size(800, 1400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final store = QboxStore();
      await tester.pumpWidget(
        MaterialApp(
          home: WelcomeScreen(store: store),
        ),
      );

      await tester.ensureVisible(find.text('Sign Up').last);
      await tester.tap(find.text('Sign Up').last);
      await tester.pumpAndSettle();

      expect(find.byType(CustomerSignUpScreen), findsOneWidget);
      expect(find.text('Customer Registration'), findsOneWidget);
    });

    testWidgets('navigates to Customer Login screen', (tester) async {
      tester.view.physicalSize = const Size(800, 1400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final store = QboxStore();
      await tester.pumpWidget(
        MaterialApp(
          home: WelcomeScreen(store: store),
        ),
      );

      await tester.ensureVisible(find.text('Login').last);
      await tester.tap(find.text('Login').last);
      await tester.pumpAndSettle();

      expect(find.byType(CustomerLoginScreen), findsOneWidget);
      expect(find.text('Customer Login'), findsOneWidget);
      expect(find.text('Welcome to Qbox Customer'), findsOneWidget);
    });
  });

  group('Shopkeeper Sign Up Flow Widget Tests', () {
    testWidgets('validates mandatory fields on empty submit', (tester) async {
      tester.view.physicalSize = const Size(800, 1600);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final store = QboxStore();
      await tester.pumpWidget(
        MaterialApp(
          home: ShopkeeperSignUpScreen(store: store),
        ),
      );

      await tester.ensureVisible(find.text('Register & Open Shop'));
      await tester.tap(find.text('Register & Open Shop'));
      await tester.pumpAndSettle();

      expect(find.text('Full name is required'), findsOneWidget);
      expect(find.text('Shop name is required'), findsOneWidget);
      expect(find.text('Shop address is required'), findsOneWidget);
      expect(find.text('Phone number is required'), findsOneWidget);
    });

    testWidgets('validates invalid phone and invalid UPI ID', (tester) async {
      tester.view.physicalSize = const Size(800, 1600);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final store = QboxStore();
      await tester.pumpWidget(
        MaterialApp(
          home: ShopkeeperSignUpScreen(store: store),
        ),
      );

      await tester.enterText(find.widgetWithText(TextFormField, 'Phone Number *'), '12345');
      await tester.enterText(find.widgetWithText(TextFormField, 'UPI ID (Optional)'), 'not_a_valid_upi');

      await tester.ensureVisible(find.text('Register & Open Shop'));
      await tester.tap(find.text('Register & Open Shop'));
      await tester.pumpAndSettle();

      expect(find.text('Enter a valid 10-digit mobile number (starts with 6-9)'), findsOneWidget);
      expect(find.text('Enter a valid UPI ID (e.g. shopname@upi or 9876543210@paytm)'), findsOneWidget);
    });

    testWidgets('supports QR selection and preview display', (tester) async {
      tester.view.physicalSize = const Size(800, 1600);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final store = QboxStore();
      final mockPicker = MockImagePicker(fileToReturn: createMockQrFile());

      await tester.pumpWidget(
        MaterialApp(
          home: ShopkeeperSignUpScreen(store: store, imagePicker: mockPicker),
        ),
      );

      expect(find.text('No Payment QR Uploaded'), findsOneWidget);
      expect(find.byType(QrPreviewCard), findsNothing);

      await tester.ensureVisible(find.text('Upload from Gallery'));
      await tester.tap(find.text('Upload from Gallery'));
      await tester.pumpAndSettle();

      expect(find.byType(QrPreviewCard), findsOneWidget);
      expect(find.text('bhim_store_standee_qr.png'), findsOneWidget);
      expect(find.text('BHIM UPI PREVIEW'), findsOneWidget);

      await tester.tap(find.text('Remove'));
      await tester.pumpAndSettle();

      expect(find.byType(QrPreviewCard), findsNothing);
      expect(find.text('No Payment QR Uploaded'), findsOneWidget);
    });

    testWidgets('submits valid registration and navigates to shop dashboard', (tester) async {
      tester.view.physicalSize = const Size(800, 1600);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final store = QboxStore();
      final mockPicker = MockImagePicker(fileToReturn: createMockQrFile());

      ApiService.mockShopkeeperRegisterResult = ApiResult.success(
        ShopkeeperProfile(
          fullName: 'Ramesh Chandra',
          shopName: 'Chandra Kirana',
          shopAddress: '12 Market Road, Bengaluru',
          phone: '+919876543210',
          userId: 'shopkeeper-uuid-1',
          shopId: 'shop-uuid-1',
          upiId: 'chandrakirana@upi',
          qrCodeName: 'test_qr.png',
          hasPaymentQr: true,
          accessToken: 'test-shopkeeper-access-token',
          refreshToken: 'test-shopkeeper-refresh-token',
        ),
      );
      addTearDown(ApiService.resetTestMocks);

      await tester.pumpWidget(
        MaterialApp(
          home: ShopkeeperSignUpScreen(store: store, imagePicker: mockPicker),
        ),
      );

      await tester.enterText(find.widgetWithText(TextFormField, 'Full Name *'), 'Ramesh Chandra');
      await tester.enterText(find.widgetWithText(TextFormField, 'Shop / Business Name *'), 'Chandra Kirana');
      await tester.enterText(find.widgetWithText(TextFormField, 'Shop Address *'), '12 Market Road, Bengaluru');
      await tester.enterText(find.widgetWithText(TextFormField, 'Phone Number *'), '9876543210');
      await tester.enterText(find.widgetWithText(TextFormField, 'Account Password *'), 'QboxSecure@2026');
      await tester.enterText(find.widgetWithText(TextFormField, 'UPI ID (Optional)'), 'chandrakirana@upi');

      // Upload mandatory payment QR code from gallery
      await tester.ensureVisible(find.text('Upload from Gallery'));
      await tester.tap(find.text('Upload from Gallery'));
      await tester.pumpAndSettle();

      await tester.ensureVisible(find.text('Register & Open Shop'));
      await tester.tap(find.text('Register & Open Shop'));
      await tester.pumpAndSettle();

      expect(find.byType(HomeScreen), findsOneWidget);
      expect(find.text('Chandra Kirana'), findsOneWidget);
      expect(store.shopkeeperProfile, isNotNull);
      expect(store.shopkeeperProfile!.shopName, 'Chandra Kirana');
      expect(store.isAuthenticated, isTrue);
    });
  });

  group('Shopkeeper Login Flow Widget Tests', () {
    testWidgets('logs in via real backend auth flow and opens dashboard', (tester) async {
      tester.view.physicalSize = const Size(800, 1400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final store = QboxStore();

      ApiService.mockLoginResult = ApiResult.success(
        LoginResultData(
          accessToken: 'real-shop-access-token',
          refreshToken: 'real-shop-refresh-token',
          roles: ['SHOPKEEPER'],
          profile: ShopkeeperProfile(
            fullName: 'Ramesh Chandra',
            shopName: 'Chandra Kirana',
            shopAddress: '12 Market Road, Bengaluru',
            phone: '+919876543210',
            userId: 'shopkeeper-uuid-1',
            shopId: 'shop-uuid-1',
          ),
        ),
      );
      addTearDown(ApiService.resetTestMocks);

      await tester.pumpWidget(
        MaterialApp(
          home: ShopkeeperLoginScreen(store: store),
        ),
      );

      expect(find.text('Welcome Back, Shopkeeper'), findsOneWidget);
      await tester.enterText(find.widgetWithText(TextFormField, 'Registered Mobile Number or Email *'), '9876543210');
      await tester.enterText(find.widgetWithText(TextFormField, 'Password *'), 'SecurePassword@123');

      await tester.ensureVisible(find.text('Login to Shopkeeper Dashboard'));
      await tester.tap(find.text('Login to Shopkeeper Dashboard'));
      await tester.pumpAndSettle();

      expect(find.byType(HomeScreen), findsOneWidget);
      expect(store.isAuthenticated, isTrue);
    });
  });

  group('Customer Sign Up Flow Widget Tests', () {
    testWidgets('customer sign up contains ONLY the 3 required fields and validates', (tester) async {
      tester.view.physicalSize = const Size(800, 1400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final store = QboxStore();

      ApiService.mockCustomerRegisterResult = ApiResult.success(
        RegisteredCustomer(
          fullName: 'Sunita Devi',
          phone: '+919988776655',
          address: 'Flat 401, Bengaluru',
          userId: 'cust-sunita-1',
          accessToken: 'cust-access-token-1',
          refreshToken: 'cust-refresh-token-1',
        ),
      );
      addTearDown(ApiService.resetTestMocks);

      await tester.pumpWidget(
        MaterialApp(
          home: CustomerSignUpScreen(store: store),
        ),
      );

      expect(find.byType(TextFormField), findsNWidgets(3));
      expect(find.widgetWithText(TextFormField, 'Full Name *'), findsOneWidget);
      expect(find.widgetWithText(TextFormField, 'Phone Number *'), findsOneWidget);
      expect(find.widgetWithText(TextFormField, 'Home / Delivery Address *'), findsOneWidget);

      await tester.ensureVisible(find.text('Register as Customer'));
      await tester.tap(find.text('Register as Customer'));
      await tester.pumpAndSettle();

      expect(find.text('Full name is required'), findsOneWidget);
      expect(find.text('Phone number is required'), findsOneWidget);
      expect(find.text('Address is required'), findsOneWidget);

      await tester.enterText(find.widgetWithText(TextFormField, 'Full Name *'), 'Sunita Devi');
      await tester.enterText(find.widgetWithText(TextFormField, 'Phone Number *'), '9988776655');
      await tester.enterText(find.widgetWithText(TextFormField, 'Home / Delivery Address *'), 'Flat 401, Bengaluru');

      await tester.ensureVisible(find.text('Register as Customer'));
      await tester.tap(find.text('Register as Customer'));
      await tester.pumpAndSettle();

      expect(find.byType(CustomerHomeScreen), findsOneWidget);
      expect(find.byType(HomeScreen), findsNothing);
      expect(find.text('Sunita Devi'), findsOneWidget);
      expect(store.isAuthenticated, isTrue);
    });
  });

  group('Customer Login & Home Screen Widget Tests', () {
    testWidgets('customer login opens CustomerHomeScreen placeholder and prevents merchant access', (tester) async {
      tester.view.physicalSize = const Size(800, 1400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final store = QboxStore();

      ApiService.mockLoginResult = ApiResult.success(
        LoginResultData(
          accessToken: 'real-cust-access-token',
          refreshToken: 'real-cust-refresh-token',
          roles: ['CUSTOMER'],
          profile: ShopkeeperProfile(
            fullName: 'Sravani Customer',
            shopName: '',
            shopAddress: 'Bengaluru',
            phone: '+919123456780',
            userId: 'cust-uuid-2',
          ),
        ),
      );
      addTearDown(ApiService.resetTestMocks);

      await tester.pumpWidget(
        MaterialApp(
          home: CustomerLoginScreen(store: store),
        ),
      );

      expect(find.text('Welcome to Qbox Customer'), findsOneWidget);
      await tester.enterText(find.widgetWithText(TextFormField, 'Customer Mobile Number *'), '9123456780');

      await tester.ensureVisible(find.text('Login to Customer Portal'));
      await tester.tap(find.text('Login to Customer Portal'));
      await tester.pumpAndSettle();

      expect(find.byType(CustomerHomeScreen), findsOneWidget);
      expect(find.byType(HomeScreen), findsNothing);
      expect(find.text('Sravani Customer'), findsOneWidget);
      expect(
        find.text('Customer Portal: You are viewing customer records. Merchant ledger editing is disabled.'),
        findsOneWidget,
      );
    });

    testWidgets('customer home screen displays linked store khata with paise formatting', (tester) async {
      tester.view.physicalSize = const Size(800, 1400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final store = QboxStore(
        initialCustomers: [
          Customer(
            id: 2,
            name: 'Sravani',
            phone: '91234 56780',
            balancePaise: 7500,
          )..entries.add(
              LedgerEntry(
                id: 3,
                amountPaise: 7500,
                isCredit: true,
                note: 'Milk and provisions',
                createdAt: DateTime.now(),
              ),
            ),
        ],
      );
      final customer = RegisteredCustomer(
        fullName: 'Sravani',
        phone: '91234 56780',
        address: 'Bengaluru',
      );

      await tester.pumpWidget(
        MaterialApp(
          home: CustomerHomeScreen(customer: customer, store: store),
        ),
      );

      expect(find.text('Your Active Khata with Shopkeeper'), findsOneWidget);
      expect(find.text('₹75.00'), findsOneWidget);
      expect(find.text('Milk and provisions'), findsOneWidget);
    });
  });

  group('Logout & Navigation Stack Flow Tests', () {
    testWidgets('Shopkeeper top-right logout icon shows confirmation dialog with Cancel & Logout', (tester) async {
      tester.view.physicalSize = const Size(800, 1400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final store = QboxStore();
      store.setShopkeeper(
        ShopkeeperProfile(
          fullName: 'Ramesh',
          shopName: 'Chandra Store',
          shopAddress: 'Market Road',
          phone: '9876543210',
        ),
      );

      await tester.pumpWidget(
        MaterialApp(
          home: HomeScreen(store: store),
        ),
      );

      // Verify dashboard is displayed and user is authenticated
      expect(find.byType(HomeScreen), findsOneWidget);
      expect(store.isAuthenticated, isTrue);

      // Tap top-right logout icon
      final logoutIcon = find.byIcon(Icons.logout_rounded);
      expect(logoutIcon, findsOneWidget);
      await tester.tap(logoutIcon);
      await tester.pumpAndSettle();

      // Verify confirmation dialog
      expect(find.byType(AlertDialog), findsOneWidget);
      expect(find.text('Are you sure you want to log out?'), findsOneWidget);
      expect(find.widgetWithText(TextButton, 'Cancel'), findsOneWidget);
      expect(find.widgetWithText(FilledButton, 'Logout'), findsOneWidget);

      // Select Cancel
      await tester.tap(find.widgetWithText(TextButton, 'Cancel'));
      await tester.pumpAndSettle();

      // Verify user remains on the dashboard and session is NOT cleared
      expect(find.byType(AlertDialog), findsNothing);
      expect(find.byType(HomeScreen), findsOneWidget);
      expect(store.isAuthenticated, isTrue);
    });

    testWidgets('Shopkeeper logout clears session, preserves data and navigates to WelcomeScreen without back history', (tester) async {
      tester.view.physicalSize = const Size(800, 1400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final store = QboxStore();
      final profile = ShopkeeperProfile(
        fullName: 'Ramesh Chandra',
        shopName: 'Chandra Kirana Store',
        shopAddress: 'Market Road',
        phone: '9876543210',
      );
      store.setShopkeeper(profile);

      final initialCustomersCount = store.customers.length;
      final initialOutstandingPaise = store.totalOutstandingPaise;

      await tester.pumpWidget(
        MaterialApp(
          home: HomeScreen(store: store),
        ),
      );

      // Tap logout icon
      await tester.tap(find.byIcon(Icons.logout_rounded));
      await tester.pumpAndSettle();

      // Confirm Logout
      await tester.tap(find.widgetWithText(FilledButton, 'Logout'));
      await tester.pumpAndSettle();

      // 1. Navigated to WelcomeScreen
      expect(find.byType(WelcomeScreen), findsOneWidget);
      expect(find.byType(HomeScreen), findsNothing);

      // 2. Session is cleared
      expect(store.isAuthenticated, isFalse);
      expect(store.activeSessionRole, isNull);

      // 3. Registered data and records are preserved (NOT deleted)
      expect(store.shopkeeperProfile, profile);
      expect(store.customers.length, initialCustomersCount);
      expect(store.totalOutstandingPaise, initialOutstandingPaise);

      // 4. Back navigation stack is cleared - cannot pop back to dashboard
      final welcomeElement = tester.element(find.byType(WelcomeScreen));
      expect(Navigator.canPop(welcomeElement), isFalse);
    });

    testWidgets('Customer logout shows confirmation dialog, Cancel stays, Logout clears session to WelcomeScreen', (tester) async {
      tester.view.physicalSize = const Size(800, 1400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final store = QboxStore();
      final customer = RegisteredCustomer(
        fullName: 'Sravani',
        phone: '91234 56780',
        address: 'Bengaluru',
      );
      store.setCustomer(customer);

      await tester.pumpWidget(
        MaterialApp(
          home: CustomerHomeScreen(customer: customer, store: store),
        ),
      );

      expect(find.byType(CustomerHomeScreen), findsOneWidget);
      expect(store.isAuthenticated, isTrue);

      // Tap logout icon in Customer App Bar
      await tester.tap(find.byIcon(Icons.logout_rounded));
      await tester.pumpAndSettle();

      // Verify dialog
      expect(find.text('Are you sure you want to log out?'), findsOneWidget);

      // Test Cancel keeps on CustomerHomeScreen
      await tester.tap(find.widgetWithText(TextButton, 'Cancel'));
      await tester.pumpAndSettle();
      expect(find.byType(CustomerHomeScreen), findsOneWidget);
      expect(store.isAuthenticated, isTrue);

      // Test bottom "Log Out / Switch Role" button
      await tester.ensureVisible(find.widgetWithText(OutlinedButton, 'Log Out / Switch Role'));
      await tester.tap(find.widgetWithText(OutlinedButton, 'Log Out / Switch Role'));
      await tester.pumpAndSettle();

      // Tap Logout
      await tester.tap(find.widgetWithText(FilledButton, 'Logout'));
      await tester.pumpAndSettle();

      // Navigated to WelcomeScreen
      expect(find.byType(WelcomeScreen), findsOneWidget);
      expect(find.byType(CustomerHomeScreen), findsNothing);

      // Session cleared
      expect(store.isAuthenticated, isFalse);

      // Data preserved
      expect(store.customerProfile, customer);
      expect(store.customers.isEmpty, isTrue);

      // Cannot pop back
      final welcomeElement = tester.element(find.byType(WelcomeScreen));
      expect(Navigator.canPop(welcomeElement), isFalse);
    });
  });

  group('Backend Integration & Error Handling Widget Tests', () {
    testWidgets('validates password requirement (min 8 chars) in registration form', (tester) async {
      tester.view.physicalSize = const Size(800, 1600);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final store = QboxStore();
      await tester.pumpWidget(
        MaterialApp(
          home: ShopkeeperSignUpScreen(store: store),
        ),
      );

      // Enter short password
      await tester.enterText(find.widgetWithText(TextFormField, 'Account Password *'), 'short');
      await tester.ensureVisible(find.text('Register & Open Shop'));
      await tester.tap(find.text('Register & Open Shop'));
      await tester.pumpAndSettle();

      expect(find.text('Password must be at least 8 characters'), findsOneWidget);
    });

    testWidgets('displays backend error message (e.g. 409 Mobile already registered) when registration fails', (tester) async {
      tester.view.physicalSize = const Size(800, 1600);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final store = QboxStore();
      final mockPicker = MockImagePicker(fileToReturn: createMockQrFile());
      final mockService = _MockFailingApiService(
        errorText: 'Mobile number already registered. Please login instead.',
      );

      await tester.pumpWidget(
        MaterialApp(
          home: ShopkeeperSignUpScreen(
            store: store,
            apiService: mockService,
            imagePicker: mockPicker,
          ),
        ),
      );

      await tester.enterText(find.widgetWithText(TextFormField, 'Full Name *'), 'Ramesh Chandra');
      await tester.enterText(find.widgetWithText(TextFormField, 'Shop / Business Name *'), 'Chandra Kirana');
      await tester.enterText(find.widgetWithText(TextFormField, 'Shop Address *'), '12 Market Road, Bengaluru');
      await tester.enterText(find.widgetWithText(TextFormField, 'Phone Number *'), '9876543210');
      await tester.enterText(find.widgetWithText(TextFormField, 'Account Password *'), 'SecurePassword@123');

      // Upload mandatory payment QR code from gallery
      await tester.ensureVisible(find.text('Upload from Gallery'));
      await tester.tap(find.text('Upload from Gallery'));
      await tester.pumpAndSettle();

      await tester.ensureVisible(find.text('Register & Open Shop'));
      await tester.tap(find.text('Register & Open Shop'));
      await tester.pumpAndSettle();

      // Ensure error banner is displayed
      expect(find.text('Mobile number already registered. Please login instead.'), findsWidgets);
      // Ensure user remained on registration screen
      expect(find.byType(ShopkeeperSignUpScreen), findsOneWidget);
      expect(find.byType(HomeScreen), findsNothing);
    });

    testWidgets('displays backend error banner when login credentials are invalid (401 Unauthorized)', (tester) async {
      tester.view.physicalSize = const Size(800, 1400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final store = QboxStore();
      final mockService = _MockFailingApiService(
        errorText: 'Invalid mobile number or password',
      );

      await tester.pumpWidget(
        MaterialApp(
          home: ShopkeeperLoginScreen(store: store, apiService: mockService),
        ),
      );

      await tester.enterText(find.widgetWithText(TextFormField, 'Registered Mobile Number or Email *'), '9876543210');
      await tester.enterText(find.widgetWithText(TextFormField, 'Password *'), 'WrongPassword@999');

      await tester.ensureVisible(find.text('Login to Shopkeeper Dashboard'));
      await tester.tap(find.text('Login to Shopkeeper Dashboard'));
      await tester.pumpAndSettle();

      // Ensure error message is displayed and user remains on login screen
      expect(find.text('Invalid mobile number or password'), findsWidgets);
      expect(find.byType(ShopkeeperLoginScreen), findsOneWidget);
      expect(find.byType(HomeScreen), findsNothing);
    });

    testWidgets('toggles password visibility on registration screen', (tester) async {
      tester.view.physicalSize = const Size(800, 1600);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final store = QboxStore();
      await tester.pumpWidget(
        MaterialApp(
          home: ShopkeeperSignUpScreen(store: store),
        ),
      );

      // Verify visibility toggle button exists
      expect(find.byIcon(Icons.visibility_outlined), findsOneWidget);
      await tester.tap(find.byIcon(Icons.visibility_outlined));
      await tester.pumpAndSettle();
      expect(find.byIcon(Icons.visibility_off_outlined), findsOneWidget);
    });
  });

  group('Customer Registration QR & Onboarding Flow Widget Tests', () {
    testWidgets('Welcome screen shows "Have a Shop QR Code?" action and opens Scan QR screen', (tester) async {
      tester.view.physicalSize = const Size(800, 1600);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final store = QboxStore();
      await tester.pumpWidget(MaterialApp(home: WelcomeScreen(store: store)));

      expect(find.text('Have a Shop QR Code?'), findsOneWidget);
      expect(find.widgetWithText(FilledButton, 'Scan QR'), findsOneWidget);

      await tester.tap(find.widgetWithText(FilledButton, 'Scan QR'));
      await tester.pumpAndSettle();

      expect(find.byType(ScanShopQrScreen), findsOneWidget);
      expect(find.text('Join Shop via QR'), findsOneWidget);
      expect(find.text('Registration Link or Token'), findsOneWidget);
    });

    testWidgets('ScanShopQrScreen resolves token, displays verified merchant card, and lets customer confirm join', (tester) async {
      tester.view.physicalSize = const Size(800, 1600);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final store = QboxStore();
      final customer = RegisteredCustomer(
        fullName: 'Kavita Reddy',
        phone: '9876543210',
        address: 'HSR Layout, Bengaluru',
        accessToken: 'mock-cust-jwt',
      );
      store.setCustomer(customer);

      await tester.pumpWidget(MaterialApp(
        home: ScanShopQrScreen(store: store, initialToken: 'valid-test-token-123'),
      ));
      await tester.pumpAndSettle();

      // Verified merchant details and explicit confirmation prompt
      expect(find.text('VERIFIED QBOX MERCHANT'), findsOneWidget);
      expect(find.text('Chandra Kirana & Provisions'), findsOneWidget);
      expect(find.textContaining('Do you want to connect your Qbox account with Chandra Kirana & Provisions?'), findsOneWidget);
      expect(find.text('Join Shop'), findsOneWidget);
      expect(find.text('Cancel'), findsOneWidget);

      // Confirm join
      await tester.tap(find.text('Join Shop'));
      await tester.pumpAndSettle();

      // Confirmation dialog showing zero balance
      expect(find.text('Successfully Joined!'), findsOneWidget);
      expect(find.textContaining('Initial balance: ₹0.00'), findsOneWidget);
      expect(find.text('Go to Customer Home'), findsOneWidget);

      // Tap Go to Customer Home
      await tester.tap(find.text('Go to Customer Home'));
      await tester.pumpAndSettle();

      expect(find.byType(CustomerHomeScreen), findsOneWidget);
      expect(find.text('My Connected Shops'), findsOneWidget);
    });

    testWidgets('Shopkeeper dashboard has QR icon and Onboarding QR card opening ShopQrManagementScreen', (tester) async {
      tester.view.physicalSize = const Size(800, 1600);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final store = QboxStore();
      final profile = ShopkeeperProfile(
        fullName: 'Ramesh Chandra',
        shopName: 'Chandra Kirana Store',
        shopAddress: 'Shop #4, Market Road, Bengaluru',
        phone: '9876543210',
        shopId: 'shop-uuid-1',
        accessToken: 'mock-shopkeeper-jwt',
      );
      store.setShopkeeper(profile);

      await tester.pumpWidget(MaterialApp(home: HomeScreen(store: store)));
      await tester.pumpAndSettle();

      // Check Dashboard QR Card & App Bar Icon
      expect(find.text('Customer Onboarding QR'), findsOneWidget);
      expect(find.text('View QR'), findsOneWidget);
      expect(find.byIcon(Icons.qr_code_2_rounded), findsWidgets);

      // Tap View QR
      await tester.tap(find.text('View QR'));
      await tester.pumpAndSettle();

      expect(find.byType(ShopQrManagementScreen), findsOneWidget);
      expect(find.text('ACTIVE REGISTRATION QR'), findsOneWidget);
      expect(find.text('STATIC'), findsOneWidget);
      expect(find.text('Rotate QR'), findsOneWidget);
      expect(find.text('Share URL'), findsOneWidget);
      expect(find.text('Customers Joined via QR'), findsOneWidget);
    });

    testWidgets('ShopQrManagementScreen confirms rotation with warning dialog', (tester) async {
      tester.view.physicalSize = const Size(800, 1600);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final store = QboxStore();
      final profile = ShopkeeperProfile(
        fullName: 'Ramesh Chandra',
        shopName: 'Chandra Kirana Store',
        shopAddress: 'Shop #4, Market Road, Bengaluru',
        phone: '9876543210',
        shopId: 'shop-uuid-1',
        accessToken: 'mock-shopkeeper-jwt',
      );
      store.setShopkeeper(profile);

      await tester.pumpWidget(MaterialApp(home: ShopQrManagementScreen(store: store)));
      await tester.pumpAndSettle();

      // Tap Rotate QR
      await tester.tap(find.text('Rotate QR'));
      await tester.pumpAndSettle();

      // Check warning in dialog
      expect(find.text('Rotate Registration QR?'), findsOneWidget);
      expect(find.textContaining('Any existing printed QR codes in your shop will stop working immediately.'), findsOneWidget);

      // Cancel keeps existing QR
      await tester.tap(find.text('Cancel'));
      await tester.pumpAndSettle();

      expect(find.byType(ShopQrManagementScreen), findsOneWidget);
      expect(find.text('ACTIVE REGISTRATION QR'), findsOneWidget);
    });

    testWidgets('ShopQrManagementScreen displays login action when session authentication token is invalid or expired', (tester) async {
      tester.view.physicalSize = const Size(800, 1600);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final store = QboxStore();
      final mockAuthFailingService = _MockAuthFailingApiService();

      await tester.pumpWidget(
        MaterialApp(
          home: ShopQrManagementScreen(store: store, apiService: mockAuthFailingService),
        ),
      );
      await tester.pumpAndSettle();

      // Verify that the screen handles authentication error by showing the friendly login action
      expect(find.byType(ShopQrManagementScreen), findsOneWidget);
      expect(find.text('Log In as Shopkeeper'), findsOneWidget);
      expect(find.text('Invalid or expired authentication token.'), findsOneWidget);
    });
  });

  group('Shopkeeper Dashboard Real Backend Data & State Tests', () {
    testWidgets('displays real backend customer data on DashboardPage and CustomersPage', (tester) async {
      tester.view.physicalSize = const Size(800, 1600);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(() => ApiService.mockShopCustomersResult = null);

      final store = QboxStore();
      final profile = ShopkeeperProfile(
        fullName: 'Ramesh',
        shopName: 'Ramesh Kirana',
        shopAddress: 'Market Road',
        phone: '9087654321',
        shopId: 'faae0275-5760-49c3-a6ff-2c9f15ae4519',
        accessToken: 'mock-valid-token',
      );
      store.setShopkeeper(profile, token: 'mock-valid-token');

      // Mock real customer data from backend
      ApiService.mockShopCustomersResult = ApiResult.success([
        ShopCustomerItem(
          customerId: 'cust-uuid-suresh',
          fullName: 'Suresh Kumar',
          phone: '+919898989898',
          joinedAt: '2026-11-10T12:00:00Z',
          status: 'ACTIVE',
          currentBalancePaise: 12500,
        ),
      ]);

      await tester.pumpWidget(MaterialApp(home: HomeScreen(store: store)));
      await tester.pumpAndSettle();

      // Dashboard verification
      expect(find.text('Customers'), findsWidgets);
      // Stat card shows 1 customer
      expect(find.text('1'), findsOneWidget);
      // Outstanding balance card and recent customer tile both show ₹125.00
      expect(find.text('₹125.00'), findsNWidgets(2));
      // Collected card shows ₹0.00 and 'No repayments yet'
      expect(find.text('₹0.00'), findsOneWidget);
      expect(find.text('No repayments yet'), findsOneWidget);
      // Recent customers section displays Suresh Kumar
      expect(find.text('Suresh Kumar'), findsOneWidget);
      expect(find.text('+919898989898'), findsOneWidget);

      // Navigate to Customers tab via bottom NavigationDestination
      await tester.tap(find.byType(NavigationDestination).at(1));
      await tester.pumpAndSettle();

      // Customers page displays Suresh Kumar with balance
      expect(find.text('1 customer in your shop'), findsOneWidget);
      expect(find.text('Suresh Kumar'), findsOneWidget);
      expect(find.text('+919898989898'), findsOneWidget);
      expect(find.text('₹125.00'), findsOneWidget);
    });

    testWidgets('displays empty state on dashboard and customers page when 0 customers returned', (tester) async {
      tester.view.physicalSize = const Size(800, 1600);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(() => ApiService.mockShopCustomersResult = null);

      final store = QboxStore();
      final profile = ShopkeeperProfile(
        fullName: 'Ramesh',
        shopName: 'Ramesh Kirana',
        shopAddress: 'Market Road',
        phone: '9087654321',
        shopId: 'faae0275-5760-49c3-a6ff-2c9f15ae4519',
        accessToken: 'mock-valid-token',
      );
      store.setShopkeeper(profile, token: 'mock-valid-token');

      // Backend returns empty list
      ApiService.mockShopCustomersResult = ApiResult.success([]);

      await tester.pumpWidget(MaterialApp(home: HomeScreen(store: store)));
      await tester.pumpAndSettle();

      // Dashboard empty state
      expect(find.text('0'), findsOneWidget);
      expect(find.text('₹0.00'), findsNWidgets(2)); // Total outstanding + collected
      expect(find.text('No customers joined yet'), findsOneWidget);
      expect(find.text('View Onboarding QR'), findsOneWidget);

      // Navigate to Customers tab via bottom NavigationDestination
      await tester.tap(find.byType(NavigationDestination).at(1));
      await tester.pumpAndSettle();

      // Customers page empty state
      expect(find.text('0 customers in your shop'), findsOneWidget);
      expect(find.text('No Customers Connected Yet'), findsOneWidget);
      expect(find.text('View Customer QR'), findsOneWidget);
    });

    testWidgets('displays error banner and retry button when backend API fails', (tester) async {
      tester.view.physicalSize = const Size(800, 1600);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(() => ApiService.mockShopCustomersResult = null);

      final store = QboxStore();
      final profile = ShopkeeperProfile(
        fullName: 'Ramesh',
        shopName: 'Ramesh Kirana',
        shopAddress: 'Market Road',
        phone: '9087654321',
        shopId: 'faae0275-5760-49c3-a6ff-2c9f15ae4519',
        accessToken: 'mock-valid-token',
      );
      store.setShopkeeper(profile, token: 'mock-valid-token');

      // First call fails
      ApiService.mockShopCustomersResult = ApiResult.failure('Unable to connect to server');

      await tester.pumpWidget(MaterialApp(home: HomeScreen(store: store)));
      await tester.pumpAndSettle();

      // Error banner visible with Retry button
      expect(find.text('Unable to connect to server'), findsOneWidget);
      expect(find.widgetWithText(TextButton, 'Retry'), findsOneWidget);

      // Second call succeeds
      ApiService.mockShopCustomersResult = ApiResult.success([
        ShopCustomerItem(
          customerId: 'cust-uuid-suresh',
          fullName: 'Suresh Kumar',
          phone: '+919898989898',
          joinedAt: '2026-11-10T12:00:00Z',
          status: 'ACTIVE',
          currentBalancePaise: 0,
        ),
      ]);

      await tester.tap(find.widgetWithText(TextButton, 'Retry'));
      await tester.pumpAndSettle();

      // Error cleared and customer displayed
      expect(find.text('Unable to connect to server'), findsNothing);
      expect(find.text('Suresh Kumar'), findsOneWidget);
      expect(find.text('1'), findsOneWidget);
    });

    testWidgets('confirms complete removal of demo customer data and fake totals from HomeScreen', (tester) async {
      tester.view.physicalSize = const Size(800, 1600);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(() => ApiService.mockShopCustomersResult = null);

      final store = QboxStore();
      final profile = ShopkeeperProfile(
        fullName: 'Ramesh',
        shopName: 'Ramesh Kirana',
        shopAddress: 'Market Road',
        phone: '9087654321',
        shopId: 'faae0275-5760-49c3-a6ff-2c9f15ae4519',
        accessToken: 'mock-valid-token',
      );
      store.setShopkeeper(profile, token: 'mock-valid-token');
      ApiService.mockShopCustomersResult = ApiResult.success([]);

      await tester.pumpWidget(MaterialApp(home: HomeScreen(store: store)));
      await tester.pumpAndSettle();

      // Demo banner removed
      expect(find.textContaining('Demo data only'), findsNothing);
      expect(find.textContaining('Changes stay on this device'), findsNothing);

      // Hardcoded demo customer names removed
      expect(find.text('Ramesh Kumar'), findsNothing);
      expect(find.text('Mohammed Imran'), findsNothing);

      // Hardcoded fake totals removed
      expect(find.text('₹250.00'), findsNothing);
      expect(find.text('₹615.00'), findsNothing);
    });
  });

  group('Real Database Auth & Error Handling Tests (Step 1)', () {
    testWidgets('ShopkeeperLoginScreen displays error banner on network failure and retries successfully', (tester) async {
      tester.view.physicalSize = const Size(800, 1600);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(ApiService.resetTestMocks);

      final store = QboxStore();

      // Initially fail with network error
      ApiService.mockLoginResult = ApiResult.failure('Cannot connect to backend server at 127.0.0.1:8000', isNetworkError: true);

      await tester.pumpWidget(MaterialApp(
        home: ShopkeeperLoginScreen(store: store),
      ));

      await tester.enterText(find.widgetWithText(TextFormField, 'Registered Mobile Number or Email *'), '9876543210');
      await tester.enterText(find.widgetWithText(TextFormField, 'Password *'), 'SecurePassword@123');

      await tester.ensureVisible(find.text('Login to Shopkeeper Dashboard'));
      await tester.tap(find.text('Login to Shopkeeper Dashboard'));
      await tester.pumpAndSettle();

      // Stays on login screen, no silent demo fallback
      expect(find.byType(HomeScreen), findsNothing);
      expect(find.text('Cannot connect to backend server at 127.0.0.1:8000'), findsAtLeastNWidgets(1));
      expect(find.widgetWithText(TextButton, 'Retry'), findsOneWidget);

      // Now server recovers
      ApiService.mockLoginResult = ApiResult.success(
        LoginResultData(
          accessToken: 'recovered-token',
          refreshToken: 'recovered-refresh',
          roles: ['SHOPKEEPER'],
          profile: ShopkeeperProfile(
            fullName: 'Ramesh Chandra',
            shopName: 'Chandra Kirana',
            shopAddress: 'Market Road',
            phone: '+919876543210',
            userId: 'shopkeeper-uuid',
            shopId: 'shop-uuid',
          ),
        ),
      );

      // Tap Retry
      await tester.tap(find.widgetWithText(TextButton, 'Retry'));
      await tester.pumpAndSettle();

      // Successfully enters dashboard
      expect(find.byType(HomeScreen), findsOneWidget);
      expect(store.isAuthenticated, isTrue);
    });

    testWidgets('ShopkeeperLoginScreen displays backend error on invalid credentials', (tester) async {
      tester.view.physicalSize = const Size(800, 1600);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(ApiService.resetTestMocks);

      final store = QboxStore();
      ApiService.mockLoginResult = ApiResult.failure('Incorrect mobile number or password');

      await tester.pumpWidget(MaterialApp(
        home: ShopkeeperLoginScreen(store: store),
      ));

      await tester.enterText(find.widgetWithText(TextFormField, 'Registered Mobile Number or Email *'), '9876543210');
      await tester.enterText(find.widgetWithText(TextFormField, 'Password *'), 'WrongPassword@999');

      await tester.ensureVisible(find.text('Login to Shopkeeper Dashboard'));
      await tester.tap(find.text('Login to Shopkeeper Dashboard'));
      await tester.pumpAndSettle();

      expect(find.byType(HomeScreen), findsNothing);
      expect(find.text('Incorrect mobile number or password'), findsAtLeastNWidgets(1));
      expect(store.isAuthenticated, isFalse);
    });

    testWidgets('CustomerLoginScreen displays error banner on failure and retries successfully', (tester) async {
      tester.view.physicalSize = const Size(800, 1600);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(ApiService.resetTestMocks);

      final store = QboxStore();
      ApiService.mockLoginResult = ApiResult.failure('Connection refused. Is backend running?', isNetworkError: true);

      await tester.pumpWidget(MaterialApp(
        home: CustomerLoginScreen(store: store),
      ));

      await tester.enterText(find.widgetWithText(TextFormField, 'Customer Mobile Number *'), '9123456780');

      await tester.ensureVisible(find.text('Login to Customer Portal'));
      await tester.tap(find.text('Login to Customer Portal'));
      await tester.pumpAndSettle();

      expect(find.byType(CustomerHomeScreen), findsNothing);
      expect(find.text('Connection refused. Is backend running?'), findsAtLeastNWidgets(1));
      expect(find.widgetWithText(TextButton, 'Retry'), findsOneWidget);

      // Backend recovers
      ApiService.mockLoginResult = ApiResult.success(
        LoginResultData(
          accessToken: 'cust-token',
          refreshToken: 'cust-refresh',
          roles: ['CUSTOMER'],
          profile: ShopkeeperProfile(
            fullName: 'Suresh Kumar',
            shopName: '',
            shopAddress: 'Indiranagar',
            phone: '+919123456780',
            userId: 'cust-suresh-id',
          ),
        ),
      );

      await tester.tap(find.widgetWithText(TextButton, 'Retry'));
      await tester.pumpAndSettle();

      expect(find.byType(CustomerHomeScreen), findsOneWidget);
      expect(store.isAuthenticated, isTrue);
    });

    testWidgets('CustomerSignUpScreen displays error on registration failure', (tester) async {
      tester.view.physicalSize = const Size(800, 1600);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(ApiService.resetTestMocks);

      final store = QboxStore();
      ApiService.mockCustomerRegisterResult = ApiResult.failure('A customer account with this phone number already exists.');

      await tester.pumpWidget(MaterialApp(
        home: CustomerSignUpScreen(store: store),
      ));

      await tester.enterText(find.widgetWithText(TextFormField, 'Full Name *'), 'Duplicate Customer');
      await tester.enterText(find.widgetWithText(TextFormField, 'Phone Number *'), '9123456780');
      await tester.enterText(find.widgetWithText(TextFormField, 'Home / Delivery Address *'), 'Bengaluru');

      await tester.ensureVisible(find.text('Register as Customer'));
      await tester.tap(find.text('Register as Customer'));
      await tester.pumpAndSettle();

      expect(find.byType(CustomerHomeScreen), findsNothing);
      expect(find.text('A customer account with this phone number already exists.'), findsAtLeastNWidgets(1));
      expect(find.widgetWithText(TextButton, 'Retry'), findsOneWidget);
      expect(store.isAuthenticated, isFalse);
    });
  });
}

class _MockAuthFailingApiService extends ApiService {
  @override
  Future<ApiResult<ShopRegistrationQrData>> getShopRegistrationQr(
    String? shopId, {
    required String authToken,
  }) async {
    return ApiResult.failure('Invalid or expired authentication token.');
  }
}

class _MockFailingApiService extends ApiService {
  _MockFailingApiService({required this.errorText});
  final String errorText;

  @override
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
    return ApiResult.failure(errorText);
  }

  @override
  Future<ApiResult<LoginResultData>> login({
    required String identifier,
    required String password,
  }) async {
    return ApiResult.failure(errorText);
  }
}

class MockImagePicker implements ImagePicker {
  MockImagePicker({this.fileToReturn});
  final XFile? fileToReturn;

  @override
  Future<XFile?> pickImage({
    required ImageSource source,
    double? maxWidth,
    double? maxHeight,
    int? imageQuality,
    CameraDevice preferredCameraDevice = CameraDevice.rear,
    bool requestFullMetadata = true,
  }) async {
    return fileToReturn;
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

const kTransparent1x1Png = <int>[
  0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00, 0x00, 0x00, 0x0D,
  0x49, 0x48, 0x44, 0x52, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
  0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4, 0x89, 0x00, 0x00, 0x00,
  0x0A, 0x49, 0x44, 0x41, 0x54, 0x78, 0x9C, 0x63, 0x00, 0x01, 0x00, 0x00,
  0x05, 0x00, 0x01, 0x0D, 0x0A, 0x2D, 0xB4, 0x00, 0x00, 0x00, 0x00, 0x49,
  0x45, 0x4E, 0x44, 0xAE, 0x42, 0x60, 0x82,
];

XFile createMockQrFile({String name = 'bhim_store_standee_qr.png'}) {
  return XFile.fromData(
    Uint8List.fromList(kTransparent1x1Png),
    name: name,
    path: name,
    mimeType: 'image/png',
  );
}
