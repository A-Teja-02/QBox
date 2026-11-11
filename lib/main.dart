import 'package:flutter/material.dart';
import 'models/profiles.dart';
import 'screens/scan_shop_qr_screen.dart';
import 'screens/shop_qr_management_screen.dart';
import 'screens/welcome_screen.dart';
import 'services/api_service.dart';
import 'services/deep_link_service.dart';
import 'services/token_storage_service.dart';
import 'widgets/logout_dialog.dart';

void main() => runApp(const QboxApp());

String money(int paise) {
  final rupees = paise ~/ 100;
  final cents = (paise % 100).abs().toString().padLeft(2, '0');
  final sign = paise < 0 ? '-' : '';
  return '$sign₹$rupees.$cents';
}

class Customer {
  Customer({
    required this.id,
    required this.name,
    required this.phone,
    this.balancePaise = 0,
    this.customerId,
    this.joinedAt,
  });
  final dynamic id;
  String name;
  String phone;
  int balancePaise;
  String? customerId;
  String? joinedAt;
  final List<LedgerEntry> entries = [];
}

class LedgerEntry {
  LedgerEntry({required this.id, required this.amountPaise, required this.isCredit, required this.note, required this.createdAt});
  final int id;
  final int amountPaise;
  final bool isCredit;
  final String note;
  final DateTime createdAt;
}

class QboxStore extends ChangeNotifier {
  QboxStore({List<Customer>? initialCustomers}) {
    if (initialCustomers != null) {
      customers.addAll(initialCustomers);
    }
  }

  final List<Customer> customers = [];
  bool isLoadingCustomers = false;
  String? customersError;

  ShopkeeperProfile? shopkeeperProfile;
  RegisteredCustomer? customerProfile;
  String? activeSessionRole; // 'shopkeeper' | 'customer' | null
  String? accessToken;
  String? refreshToken;
  String? pendingShopToken;
  PublicShopInfo? pendingShopInfo;

  final TokenStorageService _tokenStorage = TokenStorageService();

  bool get isAuthenticated => activeSessionRole != null;
  bool get hasServerAuth => accessToken != null && accessToken!.isNotEmpty;
  bool get isDemoSession => activeSessionRole != null && !hasServerAuth;

  int _nextCustomerId = 4;
  int _nextEntryId = 4;
  int get totalOutstandingPaise => customers.fold(0, (sum, c) => sum + c.balancePaise);
  int get totalCollectedPaise => customers.expand((c) => c.entries).where((e) => !e.isCredit).fold(0, (sum, e) => sum + e.amountPaise);

  /// Fetches real customers linked to the authenticated shopkeeper's shop from PostgreSQL via FastAPI.
  Future<void> loadShopCustomers({ApiService? apiService}) async {
    final token = accessToken;
    if (token == null || token.isEmpty) {
      isLoadingCustomers = false;
      notifyListeners();
      return;
    }

    isLoadingCustomers = true;
    customersError = null;
    notifyListeners();

    final shopId = shopkeeperProfile?.shopId ?? 'me';
    final service = apiService ?? ApiService();

    var result = await service.getShopCustomers(shopId, authToken: token);

    // If token expired, attempt seamless refresh
    if (!result.isSuccess &&
        (result.errorMessage?.contains('401') == true ||
            result.errorMessage?.toLowerCase().contains('unauthorized') == true ||
            result.errorMessage?.toLowerCase().contains('expired') == true) &&
        refreshToken != null &&
        refreshToken!.isNotEmpty) {
      final refreshRes = await service.refreshAccessToken(refreshToken!);
      if (refreshRes.isSuccess && refreshRes.data != null) {
        final newAccess = refreshRes.data!['access_token'] as String;
        final newRefresh = refreshRes.data!['refresh_token'] as String?;
        updateTokens(newAccess, newRefreshToken: newRefresh);
        result = await service.getShopCustomers(shopId, authToken: newAccess);
      }
    }

    if (result.isSuccess) {
      customers.clear();
      final items = result.data ?? [];
      for (int i = 0; i < items.length; i++) {
        final item = items[i];
        customers.add(Customer(
          id: item.customerId.isNotEmpty ? item.customerId : (i + 1),
          name: item.fullName.isNotEmpty ? item.fullName : 'Customer',
          phone: item.phone,
          balancePaise: item.currentBalancePaise,
          customerId: item.customerId,
          joinedAt: item.joinedAt,
        ));
      }
      isLoadingCustomers = false;
      customersError = null;
    } else {
      isLoadingCustomers = false;
      customersError = result.errorMessage ?? 'Failed to load customers from server.';
    }
    notifyListeners();
  }

  void setShopkeeper(ShopkeeperProfile profile, {String? token, String? refresh}) {
    shopkeeperProfile = profile;
    activeSessionRole = 'shopkeeper';
    final effectiveToken = token ?? profile.accessToken;
    accessToken = effectiveToken;
    refreshToken = refresh;

    if (effectiveToken != null && effectiveToken.isNotEmpty && refresh != null && refresh.isNotEmpty) {
      try {
        _tokenStorage.saveTokens(accessToken: effectiveToken, refreshToken: refresh);
        _tokenStorage.saveShopkeeperProfile(profile);
        _tokenStorage.saveActiveRole('shopkeeper');
      } catch (_) {
        // Handled safely if hardware secure storage fails in production
      }
    }
    notifyListeners();
  }

  void updateTokens(String newAccessToken, {String? newRefreshToken}) {
    accessToken = newAccessToken;
    if (newRefreshToken != null && newRefreshToken.isNotEmpty) {
      refreshToken = newRefreshToken;
    }
    if (newRefreshToken != null && newRefreshToken.isNotEmpty) {
      try {
        _tokenStorage.saveTokens(accessToken: newAccessToken, refreshToken: newRefreshToken);
      } catch (_) {}
    }
    if (shopkeeperProfile != null) {
      shopkeeperProfile = ShopkeeperProfile(
        fullName: shopkeeperProfile!.fullName,
        shopName: shopkeeperProfile!.shopName,
        shopAddress: shopkeeperProfile!.shopAddress,
        phone: shopkeeperProfile!.phone,
        email: shopkeeperProfile!.email,
        upiId: shopkeeperProfile!.upiId,
        qrCodeName: shopkeeperProfile!.qrCodeName,
        userId: shopkeeperProfile!.userId,
        shopId: shopkeeperProfile!.shopId,
        accessToken: newAccessToken,
      );
      try {
        _tokenStorage.saveShopkeeperProfile(shopkeeperProfile!);
      } catch (_) {}
    }
    notifyListeners();
  }

  void setCustomer(RegisteredCustomer customer, {String? token, String? refresh}) {
    customerProfile = customer;
    activeSessionRole = 'customer';
    final effectiveToken = token ?? customer.accessToken;
    accessToken = effectiveToken;
    refreshToken = refresh;

    if (effectiveToken != null && effectiveToken.isNotEmpty && refresh != null && refresh.isNotEmpty) {
      try {
        _tokenStorage.saveTokens(accessToken: effectiveToken, refreshToken: refresh);
        _tokenStorage.saveCustomerProfile(customer);
        _tokenStorage.saveActiveRole('customer');
      } catch (_) {}
    }
    notifyListeners();
  }

  /// Sets and persists a pending shop registration token during customer onboarding.
  Future<void> setPendingShopToken(String? token, {PublicShopInfo? shopInfo}) async {
    pendingShopToken = token;
    pendingShopInfo = shopInfo;
    if (token != null && token.isNotEmpty) {
      try {
        await _tokenStorage.savePendingShopToken(token);
      } catch (_) {}
    } else {
      try {
        await _tokenStorage.clearPendingShopToken();
      } catch (_) {}
    }
    notifyListeners();
  }

  /// Clears any pending shop registration token.
  Future<void> clearPendingShopToken() async {
    pendingShopToken = null;
    pendingShopInfo = null;
    try {
      await _tokenStorage.clearPendingShopToken();
    } catch (_) {}
    notifyListeners();
  }

  /// Restores persisted authentication state from secure hardware storage on app launch.
  Future<void> initializeFromStorage() async {
    final access = await _tokenStorage.getAccessToken();
    final refresh = await _tokenStorage.getRefreshToken();
    final role = await _tokenStorage.getActiveRole();
    final pendingToken = await _tokenStorage.getPendingShopToken();

    if (pendingToken != null && pendingToken.isNotEmpty) {
      pendingShopToken = pendingToken;
    }

    if (access != null && access.isNotEmpty && refresh != null && refresh.isNotEmpty) {
      accessToken = access;
      refreshToken = refresh;
      activeSessionRole = role;

      if (role == 'shopkeeper') {
        final profile = await _tokenStorage.getShopkeeperProfile();
        if (profile != null) {
          shopkeeperProfile = profile;
        }
      } else if (role == 'customer') {
        final cust = await _tokenStorage.getCustomerProfile();
        if (cust != null) {
          customerProfile = cust;
        }
      }
      notifyListeners();
    }
  }

  /// Clears the active demo/authenticated session without deleting users, shops, customers or transaction records.
  /// Also clears hardware secure storage and issues a server-side session invalidation if authenticated.
  void logout({ApiService? apiService}) {
    final token = accessToken;
    final refresh = refreshToken;
    activeSessionRole = null;
    accessToken = null;
    refreshToken = null;
    customers.clear();
    isLoadingCustomers = false;
    customersError = null;
    notifyListeners();

    try {
      _tokenStorage.clearAll();
    } catch (_) {}
    if (token != null && token.isNotEmpty) {
      (apiService ?? ApiService())
          .logout(authToken: token, refreshToken: refresh)
          .catchError((_) => ApiResult<bool>.failure('Logout error'));
    }
  }

  Future<void> logoutAsync({ApiService? apiService}) async {
    final token = accessToken;
    final refresh = refreshToken;
    activeSessionRole = null;
    accessToken = null;
    refreshToken = null;
    customers.clear();
    isLoadingCustomers = false;
    customersError = null;
    notifyListeners();

    try {
      await _tokenStorage.clearAll();
    } catch (_) {}
    if (token != null && token.isNotEmpty) {
      await (apiService ?? ApiService()).logout(authToken: token, refreshToken: refresh);
    }
  }

  void addCustomer(String name, String phone) {
    customers.add(Customer(id: _nextCustomerId++, name: name.trim(), phone: phone.trim()));
    notifyListeners();
  }

  void addEntry(Customer customer, int amountPaise, bool isCredit, String note) {
    if (amountPaise <= 0) throw ArgumentError('Amount must be greater than zero');
    customer.entries.insert(0, LedgerEntry(id: _nextEntryId++, amountPaise: amountPaise, isCredit: isCredit, note: note.trim().isEmpty ? (isCredit ? 'Udhaar' : 'Repayment') : note.trim(), createdAt: DateTime.now()));
    customer.balancePaise += isCredit ? amountPaise : -amountPaise;
    if (customer.balancePaise < 0) {
      customer.balancePaise += isCredit ? -amountPaise : amountPaise;
      customer.entries.removeAt(0);
      throw ArgumentError('Repayment cannot exceed outstanding balance');
    }
    notifyListeners();
  }
}

class QboxApp extends StatefulWidget {
  const QboxApp({super.key});
  @override
  State<QboxApp> createState() => _QboxAppState();
}

class _QboxAppState extends State<QboxApp> {
  final store = QboxStore();
  final _deepLinkService = DeepLinkService();
  static final GlobalKey<NavigatorState> navigatorKey = GlobalKey<NavigatorState>();

  @override
  void initState() {
    super.initState();
    _deepLinkService.initialize(onTokenReceived: _handleIncomingToken);
  }

  void _handleIncomingToken(String token) {
    if (token.isEmpty) return;
    navigatorKey.currentState?.push(
      MaterialPageRoute(
        builder: (_) => ScanShopQrScreen(
          store: store,
          initialToken: token,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
    animation: store,
    builder: (context, _) => MaterialApp(
      navigatorKey: navigatorKey,
      debugShowCheckedModeBanner: false,
      title: 'Qbox Shopkeeper',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF176B5B)),
        useMaterial3: true,
        scaffoldBackgroundColor: const Color(0xFFF6F8F7),
      ),
      home: WelcomeScreen(store: store),
    ),
  );
}

class HomeScreen extends StatefulWidget {
  const HomeScreen({
    super.key,
    required this.store,
    this.apiService,
  });

  final QboxStore store;
  final ApiService? apiService;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int tab = 0;
  late final ApiService _apiService = widget.apiService ?? ApiService();

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        widget.store.loadShopCustomers(apiService: _apiService);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: widget.store,
      builder: (context, _) {
        final shopTitle = widget.store.shopkeeperProfile?.shopName ?? 'Qbox';
        final pages = [
          DashboardPage(
            store: widget.store,
            apiService: _apiService,
            onCustomers: () => setState(() => tab = 1),
          ),
          CustomersPage(
            store: widget.store,
            apiService: _apiService,
          ),
          LedgerPage(store: widget.store),
        ];
        return PopScope(
          canPop: false,
          onPopInvokedWithResult: (didPop, result) {
            if (didPop) return;
            showLogoutConfirmationDialog(context: context, store: widget.store);
          },
          child: Scaffold(
            appBar: AppBar(
              title: Text(shopTitle, style: const TextStyle(fontWeight: FontWeight.w800)),
              actions: [
                IconButton(
                  icon: const Icon(Icons.qr_code_2_rounded),
                  tooltip: 'Registration QR',
                  onPressed: () {
                    Navigator.push(
                      context,
                      MaterialPageRoute(builder: (_) => ShopQrManagementScreen(store: widget.store)),
                    );
                  },
                ),
                IconButton(
                  icon: const Icon(Icons.logout_rounded),
                  tooltip: 'Logout',
                  onPressed: () {
                    showLogoutConfirmationDialog(context: context, store: widget.store);
                  },
                ),
                const SizedBox(width: 4),
              ],
            ),
            body: SafeArea(child: pages[tab]),
            bottomNavigationBar: NavigationBar(
              selectedIndex: tab,
              onDestinationSelected: (v) => setState(() => tab = v),
              destinations: const [
                NavigationDestination(icon: Icon(Icons.dashboard_outlined), selectedIcon: Icon(Icons.dashboard), label: 'Home'),
                NavigationDestination(icon: Icon(Icons.people_outline), selectedIcon: Icon(Icons.people), label: 'Customers'),
                NavigationDestination(icon: Icon(Icons.receipt_long_outlined), selectedIcon: Icon(Icons.receipt_long), label: 'Ledger'),
              ],
            ),
          ),
        );
      },
    );
  }
}

class DashboardPage extends StatelessWidget {
  const DashboardPage({
    super.key,
    required this.store,
    this.apiService,
    required this.onCustomers,
  });

  final QboxStore store;
  final ApiService? apiService;
  final VoidCallback onCustomers;

  @override
  Widget build(BuildContext context) {
    final effectiveService = apiService ?? ApiService();

    return RefreshIndicator(
      color: const Color(0xFF176B5B),
      onRefresh: () => store.loadShopCustomers(apiService: effectiveService),
      child: ListView(
        padding: const EdgeInsets.all(18),
        children: [
          Text(
            store.shopkeeperProfile != null
                ? 'Welcome, ${store.shopkeeperProfile!.fullName} 👋'
                : 'Good morning 👋',
            style: const TextStyle(fontSize: 14, color: Colors.black54),
          ),
          const Text('Your shop at a glance', style: TextStyle(fontSize: 23, fontWeight: FontWeight.w800)),
          const SizedBox(height: 16),

          // Total Udhaar Outstanding Card
          Container(
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
              color: const Color(0xFF176B5B),
              borderRadius: BorderRadius.circular(22),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'TOTAL UDHAAR OUTSTANDING',
                  style: TextStyle(color: Colors.white70, fontSize: 11, letterSpacing: 1),
                ),
                const SizedBox(height: 8),
                Text(
                  money(store.totalOutstandingPaise),
                  style: const TextStyle(color: Colors.white, fontSize: 32, fontWeight: FontWeight.w800),
                ),
                const SizedBox(height: 14),
                Row(
                  children: [
                    const Icon(Icons.people_alt_outlined, color: Colors.white70, size: 18),
                    const SizedBox(width: 6),
                    Text(
                      '${store.customers.length} customer${store.customers.length == 1 ? '' : 's'}',
                      style: const TextStyle(color: Colors.white),
                    ),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(height: 14),

          // Static Customer Registration QR Card
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(18),
              border: Border.all(color: const Color(0xFF176B5B).withValues(alpha: 0.25)),
            ),
            child: Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: const Color(0xFFE2F1ED),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: const Icon(Icons.qr_code_2_rounded, color: Color(0xFF176B5B), size: 28),
                ),
                const SizedBox(width: 14),
                const Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Customer Onboarding QR',
                        style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14, color: Color(0xFF176B5B)),
                      ),
                      SizedBox(height: 2),
                      Text(
                        'Permanent static QR for customer credit registration',
                        style: TextStyle(fontSize: 11, color: Colors.black54),
                      ),
                    ],
                  ),
                ),
                FilledButton(
                  style: FilledButton.styleFrom(
                    backgroundColor: const Color(0xFF176B5B),
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                  ),
                  onPressed: () {
                    Navigator.push(
                      context,
                      MaterialPageRoute(builder: (_) => ShopQrManagementScreen(store: store)),
                    );
                  },
                  child: const Text('View QR', style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold)),
                ),
              ],
            ),
          ),
          const SizedBox(height: 14),

          // Loading progress indicator
          if (store.isLoadingCustomers)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 8),
              child: Center(
                child: LinearProgressIndicator(
                  color: Color(0xFF176B5B),
                  backgroundColor: Color(0xFFE2F1ED),
                ),
              ),
            ),

          // Error banner with Retry
          if (store.customersError != null)
            Container(
              margin: const EdgeInsets.only(bottom: 14),
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.red.shade50,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: Colors.red.shade200),
              ),
              child: Row(
                children: [
                  Icon(Icons.error_outline, color: Colors.red.shade700, size: 22),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      store.customersError!,
                      style: TextStyle(color: Colors.red.shade900, fontSize: 12),
                    ),
                  ),
                  TextButton(
                    onPressed: () => store.loadShopCustomers(apiService: effectiveService),
                    child: const Text('Retry'),
                  ),
                ],
              ),
            ),

          // Stat Cards
          Row(
            children: [
              Expanded(
                child: _StatCard(
                  title: 'Customers',
                  value: '${store.customers.length}',
                  icon: Icons.people_outline,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: _StatCard(
                  title: 'Collected',
                  value: money(store.totalCollectedPaise),
                  subtitle: store.totalCollectedPaise == 0 ? 'No repayments yet' : null,
                  icon: Icons.south_west,
                ),
              ),
            ],
          ),
          const SizedBox(height: 22),

          // Recent customers section
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text('Recent customers', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
              if (store.customers.isNotEmpty)
                TextButton(onPressed: onCustomers, child: const Text('View all')),
            ],
          ),
          const SizedBox(height: 8),

          if (store.customers.isEmpty && !store.isLoadingCustomers)
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: const Color(0xFFE0E5E3)),
              ),
              child: Column(
                children: [
                  const Icon(Icons.people_outline, size: 40, color: Color(0xFF176B5B)),
                  const SizedBox(height: 10),
                  const Text(
                    'No customers joined yet',
                    style: TextStyle(fontWeight: FontWeight.bold, fontSize: 15),
                  ),
                  const SizedBox(height: 4),
                  const Text(
                    'Share your Customer Onboarding QR code to register customers and track credit.',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: Colors.black54, fontSize: 12),
                  ),
                  const SizedBox(height: 12),
                  OutlinedButton.icon(
                    icon: const Icon(Icons.qr_code_2_rounded, size: 18),
                    label: const Text('View Onboarding QR'),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: const Color(0xFF176B5B),
                      side: const BorderSide(color: Color(0xFF176B5B)),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                    ),
                    onPressed: () {
                      Navigator.push(
                        context,
                        MaterialPageRoute(builder: (_) => ShopQrManagementScreen(store: store)),
                      );
                    },
                  ),
                ],
              ),
            )
          else
            ...store.customers.take(3).map(
                  (c) => CustomerTile(
                    customer: c,
                    onTap: () => Navigator.push(
                      context,
                      MaterialPageRoute(
                        builder: (_) => CustomerDetailPage(store: store, customer: c),
                      ),
                    ),
                  ),
                ),
        ],
      ),
    );
  }
}

class _StatCard extends StatelessWidget {
  const _StatCard({
    required this.title,
    required this.value,
    this.subtitle,
    required this.icon,
  });

  final String title;
  final String value;
  final String? subtitle;
  final IconData icon;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(15),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(18),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, color: const Color(0xFF176B5B)),
            const SizedBox(height: 12),
            Text(value, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 19)),
            Text(title, style: const TextStyle(color: Colors.black54, fontSize: 12)),
            if (subtitle != null) ...[
              const SizedBox(height: 2),
              Text(subtitle!, style: const TextStyle(color: Colors.black38, fontSize: 10)),
            ],
          ],
        ),
      );
}

class CustomersPage extends StatelessWidget {
  const CustomersPage({
    super.key,
    required this.store,
    this.apiService,
  });

  final QboxStore store;
  final ApiService? apiService;

  @override
  Widget build(BuildContext context) {
    final effectiveService = apiService ?? ApiService();

    return Scaffold(
      backgroundColor: Colors.transparent,
      floatingActionButton: FloatingActionButton.extended(
        backgroundColor: const Color(0xFF176B5B),
        onPressed: () {
          Navigator.push(
            context,
            MaterialPageRoute(builder: (_) => ShopQrManagementScreen(store: store)),
          );
        },
        icon: const Icon(Icons.qr_code_2_rounded, color: Colors.white),
        label: const Text('Onboarding QR', style: TextStyle(color: Colors.white)),
      ),
      body: RefreshIndicator(
        color: const Color(0xFF176B5B),
        onRefresh: () => store.loadShopCustomers(apiService: effectiveService),
        child: ListView(
          padding: const EdgeInsets.all(18),
          children: [
            const Text('Customers', style: TextStyle(fontSize: 24, fontWeight: FontWeight.w800)),
            const SizedBox(height: 6),
            Text(
              '${store.customers.length} customer${store.customers.length == 1 ? '' : 's'} in your shop',
              style: const TextStyle(color: Colors.black54),
            ),
            const SizedBox(height: 16),

            if (store.isLoadingCustomers)
              const Padding(
                padding: EdgeInsets.all(32),
                child: Center(
                  child: CircularProgressIndicator(color: Color(0xFF176B5B)),
                ),
              )
            else if (store.customersError != null)
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: Colors.red.shade50,
                  borderRadius: BorderRadius.circular(14),
                  border: Border.all(color: Colors.red.shade200),
                ),
                child: Column(
                  children: [
                    Icon(Icons.error_outline, color: Colors.red.shade700, size: 36),
                    const SizedBox(height: 8),
                    Text(
                      store.customersError!,
                      textAlign: TextAlign.center,
                      style: TextStyle(color: Colors.red.shade900, fontSize: 13),
                    ),
                    const SizedBox(height: 12),
                    FilledButton(
                      style: FilledButton.styleFrom(backgroundColor: const Color(0xFF176B5B)),
                      onPressed: () => store.loadShopCustomers(apiService: effectiveService),
                      child: const Text('Retry'),
                    ),
                  ],
                ),
              )
            else if (store.customers.isEmpty)
              Container(
                padding: const EdgeInsets.all(24),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(18),
                  border: Border.all(color: const Color(0xFFE0E5E3)),
                ),
                child: Column(
                  children: [
                    const Icon(Icons.person_search_outlined, size: 48, color: Color(0xFF176B5B)),
                    const SizedBox(height: 14),
                    const Text(
                      'No Customers Connected Yet',
                      style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
                    ),
                    const SizedBox(height: 6),
                    const Text(
                      'Customers join your shop by scanning your Customer Onboarding QR code. Tap below to view and share your QR.',
                      textAlign: TextAlign.center,
                      style: TextStyle(color: Colors.black54, fontSize: 12, height: 1.4),
                    ),
                    const SizedBox(height: 16),
                    FilledButton.icon(
                      style: FilledButton.styleFrom(
                        backgroundColor: const Color(0xFF176B5B),
                        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                      ),
                      icon: const Icon(Icons.qr_code_2_rounded, size: 20),
                      label: const Text('View Customer QR'),
                      onPressed: () {
                        Navigator.push(
                          context,
                          MaterialPageRoute(builder: (_) => ShopQrManagementScreen(store: store)),
                        );
                      },
                    ),
                  ],
                ),
              )
            else
              ...store.customers.map(
                (c) => CustomerTile(
                  customer: c,
                  onTap: () => Navigator.push(
                    context,
                    MaterialPageRoute(builder: (_) => CustomerDetailPage(store: store, customer: c)),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class CustomerTile extends StatelessWidget {
  const CustomerTile({super.key, required this.customer, required this.onTap}); final Customer customer; final VoidCallback onTap;
  @override
  Widget build(BuildContext context) => Card(color: Colors.white, elevation: 0, margin: const EdgeInsets.only(bottom: 9), child: ListTile(onTap: onTap, leading: CircleAvatar(backgroundColor: const Color(0xFFE2F1ED), child: Text(customer.name.characters.first.toUpperCase(), style: const TextStyle(color: Color(0xFF176B5B), fontWeight: FontWeight.bold))), title: Text(customer.name, style: const TextStyle(fontWeight: FontWeight.w600)), subtitle: Text(customer.phone), trailing: Column(mainAxisAlignment: MainAxisAlignment.center, crossAxisAlignment: CrossAxisAlignment.end, children: [Text(money(customer.balancePaise), style: const TextStyle(fontWeight: FontWeight.bold)), const Text('Due', style: TextStyle(fontSize: 11, color: Colors.black45))])));
}

class CustomerDetailPage extends StatelessWidget {
  const CustomerDetailPage({super.key, required this.store, required this.customer}); final QboxStore store; final Customer customer;
  @override
  Widget build(BuildContext context) => Scaffold(appBar: AppBar(title: const Text('Customer details')), body: ListView(padding: const EdgeInsets.all(18), children: [Text(customer.name, style: const TextStyle(fontSize: 24, fontWeight: FontWeight.bold)), Text(customer.phone, style: const TextStyle(color: Colors.black54)), const SizedBox(height: 18), Container(padding: const EdgeInsets.all(20), decoration: BoxDecoration(color: const Color(0xFF176B5B), borderRadius: BorderRadius.circular(18)), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [const Text('OUTSTANDING BALANCE', style: TextStyle(color: Colors.white70, fontSize: 11)), const SizedBox(height: 8), Text(money(customer.balancePaise), style: const TextStyle(color: Colors.white, fontSize: 30, fontWeight: FontWeight.bold))])), const SizedBox(height: 14), Row(children: [Expanded(child: FilledButton.icon(onPressed: () => showDialog(context: context, builder: (_) => EntryDialog(store: store, customer: customer, isCredit: true)), icon: const Icon(Icons.add), label: const Text('Add Udhaar'))), const SizedBox(width: 10), Expanded(child: OutlinedButton.icon(onPressed: customer.balancePaise == 0 ? null : () => showDialog(context: context, builder: (_) => EntryDialog(store: store, customer: customer, isCredit: false)), icon: const Icon(Icons.payments_outlined), label: const Text('Repayment')))]), const SizedBox(height: 22), const Text('Transaction history', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)), const SizedBox(height: 8), if (customer.entries.isEmpty) const Text('No transactions yet') else ...customer.entries.map((e) => Card(color: Colors.white, elevation: 0, child: ListTile(leading: Icon(e.isCredit ? Icons.call_made : Icons.call_received, color: e.isCredit ? Colors.deepOrange : Colors.green), title: Text(e.note), subtitle: Text('${e.createdAt.day}/${e.createdAt.month}/${e.createdAt.year}'), trailing: Text('${e.isCredit ? '+' : '-'}${money(e.amountPaise)}', style: const TextStyle(fontWeight: FontWeight.bold))))) ]));
}

class AddCustomerDialog extends StatefulWidget { const AddCustomerDialog({super.key, required this.store}); final QboxStore store; @override State<AddCustomerDialog> createState() => _AddCustomerDialogState(); }
class _AddCustomerDialogState extends State<AddCustomerDialog> { final name = TextEditingController(); final phone = TextEditingController(); @override void dispose(){name.dispose();phone.dispose();super.dispose();} @override Widget build(BuildContext context) => AlertDialog(title: const Text('Add customer'), content: Column(mainAxisSize: MainAxisSize.min, children: [TextField(controller: name, decoration: const InputDecoration(labelText: 'Customer name')), TextField(controller: phone, keyboardType: TextInputType.phone, decoration: const InputDecoration(labelText: 'Phone number'))]), actions: [TextButton(onPressed: ()=>Navigator.pop(context), child: const Text('Cancel')), FilledButton(onPressed: () { if(name.text.trim().isEmpty || phone.text.trim().isEmpty) return; widget.store.addCustomer(name.text, phone.text); Navigator.pop(context); }, child: const Text('Save'))]); }

class EntryDialog extends StatefulWidget { const EntryDialog({super.key, required this.store, required this.customer, required this.isCredit}); final QboxStore store; final Customer customer; final bool isCredit; @override State<EntryDialog> createState() => _EntryDialogState(); }
class _EntryDialogState extends State<EntryDialog> { final amount = TextEditingController(); final note = TextEditingController(); String? error; @override void dispose(){amount.dispose();note.dispose();super.dispose();} int? parsePaise(String raw) { final s=raw.trim(); if(!RegExp(r'^\d+(\.\d{1,2})?$').hasMatch(s)) return null; final parts=s.split('.'); final rupees=int.tryParse(parts[0]); final cents=parts.length==1?0:int.parse(parts[1].padRight(2,'0')); if(rupees==null) return null; return rupees*100+cents; } @override Widget build(BuildContext context) => AlertDialog(title: Text(widget.isCredit?'Add Udhaar':'Record repayment'), content: Column(mainAxisSize: MainAxisSize.min, children: [TextField(controller: amount, keyboardType: const TextInputType.numberWithOptions(decimal: true), decoration: const InputDecoration(labelText: 'Amount (₹)', hintText: 'e.g. 100.50')), TextField(controller: note, decoration: const InputDecoration(labelText: 'Note (optional)')), if(error!=null) Padding(padding: const EdgeInsets.only(top:8), child: Text(error!,style: const TextStyle(color: Colors.red)))]), actions: [TextButton(onPressed: ()=>Navigator.pop(context), child: const Text('Cancel')), FilledButton(onPressed: () { final p=parsePaise(amount.text); if(p==null || p<=0){setState(()=>error='Enter a valid amount, e.g. 100.50');return;} try { widget.store.addEntry(widget.customer,p,widget.isCredit,note.text); Navigator.pop(context); } catch(e){setState(()=>error=e.toString().replaceFirst('Invalid argument(s): ',''));} }, child: const Text('Save'))]); }

class LedgerPage extends StatelessWidget { const LedgerPage({super.key, required this.store}); final QboxStore store; @override Widget build(BuildContext context) { final rows=store.customers.expand((c)=>c.entries.map((e)=>(c,e))).toList()..sort((a,b)=>b.$2.createdAt.compareTo(a.$2.createdAt)); return ListView(padding: const EdgeInsets.all(18), children: [const Text('Ledger',style:TextStyle(fontSize:24,fontWeight:FontWeight.w800)), const SizedBox(height:6), const Text('All customer transactions',style:TextStyle(color:Colors.black54)), const SizedBox(height:14), ...rows.map((r)=>Card(color:Colors.white,elevation:0,child:ListTile(title:Text(r.$1.name),subtitle:Text(r.$2.note),trailing:Text('${r.$2.isCredit?'+':'-'}${money(r.$2.amountPaise)}',style:TextStyle(fontWeight:FontWeight.bold,color:r.$2.isCredit?Colors.deepOrange:Colors.green)))))]); } }
