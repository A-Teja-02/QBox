import 'package:flutter/material.dart';
import '../main.dart';
import '../models/profiles.dart';
import '../services/api_service.dart';
import '../utils/validators.dart';
import '../widgets/customer_payment_qr_sheet.dart';
import '../widgets/logout_dialog.dart';
import 'scan_shop_qr_screen.dart';

/// Customer Home Screen.
/// Displays connected merchant shops, Udhaar ledger access, and QR onboarding.
class CustomerHomeScreen extends StatefulWidget {
  const CustomerHomeScreen({
    super.key,
    required this.customer,
    required this.store,
  });

  final RegisteredCustomer customer;
  final QboxStore store;

  @override
  State<CustomerHomeScreen> createState() => _CustomerHomeScreenState();
}

class _CustomerHomeScreenState extends State<CustomerHomeScreen> {
  final _apiService = ApiService();
  List<CustomerJoinedShop> _joinedShops = [];
  bool _isLoadingShops = true;

  @override
  void initState() {
    super.initState();
    _loadJoinedShops();
  }

  Future<void> _loadJoinedShops() async {
    final token = widget.store.accessToken ?? widget.customer.accessToken;
    if (token == null || token.isEmpty) {
      // In offline demo mode or unauthenticated session, do not make backend request
      if (mounted) setState(() => _isLoadingShops = false);
      return;
    }
    final res = await _apiService.getCustomerJoinedShops(authToken: token);
    if (!mounted) return;
    if (res.isSuccess && res.data != null) {
      setState(() {
        _joinedShops = res.data!;
        _isLoadingShops = false;
      });
    } else {
      setState(() => _isLoadingShops = false);
    }
  }

  void _onLogout(BuildContext context) {
    showLogoutConfirmationDialog(context: context, store: widget.store);
  }

  void _openScanQr() {
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => ScanShopQrScreen(store: widget.store),
      ),
    ).then((_) => _loadJoinedShops());
  }

  void _showShopPaymentQrModal(CustomerJoinedShop shop) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (ctx) => CustomerPaymentQrSheet(
        shop: shop,
        store: widget.store,
        customer: widget.customer,
        apiService: _apiService,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final normalized = Validators.normalizePhone(widget.customer.phone);
    final linkedStoreCustomer = widget.store.customers.cast<Customer?>().firstWhere(
      (c) => c != null && Validators.normalizePhone(c.phone) == normalized,
      orElse: () => null,
    );

    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, result) {
        if (didPop) return;
        showLogoutConfirmationDialog(context: context, store: widget.store);
      },
      child: Scaffold(
        backgroundColor: const Color(0xFFF6F8F7),
        appBar: AppBar(
          title: const Text(
            'Qbox Customer',
            style: TextStyle(fontWeight: FontWeight.w800),
          ),
          backgroundColor: Colors.white,
          elevation: 0,
          foregroundColor: Colors.black87,
          actions: [
            IconButton(
              icon: const Icon(Icons.qr_code_scanner, color: Color(0xFF176B5B)),
              tooltip: 'Scan Shop QR',
              onPressed: _openScanQr,
            ),
            IconButton(
              icon: const Icon(Icons.logout_rounded),
              tooltip: 'Log Out / Switch Role',
              onPressed: () => _onLogout(context),
            ),
          ],
        ),
        body: SafeArea(
          child: RefreshIndicator(
            color: const Color(0xFF176B5B),
            onRefresh: _loadJoinedShops,
            child: ListView(
              padding: const EdgeInsets.all(20),
              children: [
                // Welcome Header Card
                Container(
                  padding: const EdgeInsets.all(20),
                  decoration: BoxDecoration(
                    gradient: const LinearGradient(
                      colors: [Color(0xFF176B5B), Color(0xFF0F4B3F)],
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                    ),
                    borderRadius: BorderRadius.circular(22),
                    boxShadow: [
                      BoxShadow(
                        color: const Color(0xFF176B5B).withValues(alpha: 0.2),
                        blurRadius: 14,
                        offset: const Offset(0, 6),
                      ),
                    ],
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          CircleAvatar(
                            radius: 24,
                            backgroundColor: const Color(0xFFE2F1ED),
                            child: Text(
                              widget.customer.fullName.characters.first.toUpperCase(),
                              style: const TextStyle(
                                fontSize: 22,
                                fontWeight: FontWeight.bold,
                                color: Color(0xFF176B5B),
                              ),
                            ),
                          ),
                          const SizedBox(width: 14),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  widget.customer.fullName,
                                  style: const TextStyle(
                                    color: Colors.white,
                                    fontSize: 20,
                                    fontWeight: FontWeight.w800,
                                  ),
                                ),
                                const SizedBox(height: 2),
                                Text(
                                  widget.customer.phone.startsWith('+91')
                                      ? widget.customer.phone
                                      : '+91 ${widget.customer.phone}',
                                  style: const TextStyle(
                                    color: Colors.white70,
                                    fontSize: 13,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 8,
                              vertical: 4,
                            ),
                            decoration: BoxDecoration(
                              color: Colors.white.withValues(alpha: 0.18),
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: const Text(
                              'CUSTOMER',
                              style: TextStyle(
                                fontSize: 10,
                                fontWeight: FontWeight.w800,
                                color: Colors.white,
                                letterSpacing: 0.5,
                              ),
                            ),
                          ),
                        ],
                      ),
                      if (widget.customer.address.isNotEmpty) ...[
                        const SizedBox(height: 14),
                        const Divider(color: Colors.white24, height: 1),
                        const SizedBox(height: 10),
                        Row(
                          children: [
                            const Icon(
                              Icons.location_on_outlined,
                              size: 14,
                              color: Colors.white70,
                            ),
                            const SizedBox(width: 6),
                            Expanded(
                              child: Text(
                                widget.customer.address,
                                style: const TextStyle(
                                  color: Colors.white70,
                                  fontSize: 11,
                                ),
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                          ],
                        ),
                      ],
                    ],
                  ),
                ),
                const SizedBox(height: 14),

                // Customer notice banner
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                  decoration: BoxDecoration(
                    color: Colors.blue.shade50,
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: Colors.blue.shade200),
                  ),
                  child: Row(
                    children: [
                      Icon(Icons.info_outline, size: 18, color: Colors.blue.shade800),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          'Customer Portal: You are viewing customer records. Merchant ledger editing is disabled.',
                          style: TextStyle(fontSize: 11, color: Colors.blue.shade900),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 18),

                // Action Banner: Scan Shop QR
                InkWell(
                  onTap: _openScanQr,
                  borderRadius: BorderRadius.circular(16),
                  child: Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(16),
                      border: Border.all(color: const Color(0xFF176B5B), width: 1.5),
                      boxShadow: [
                        BoxShadow(
                          color: const Color(0xFF176B5B).withValues(alpha: 0.06),
                          blurRadius: 10,
                          offset: const Offset(0, 4),
                        ),
                      ],
                    ),
                    child: Row(
                      children: [
                        Container(
                          padding: const EdgeInsets.all(12),
                          decoration: BoxDecoration(
                            color: const Color(0xFFE2F1ED),
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: const Icon(
                            Icons.qr_code_scanner,
                            color: Color(0xFF176B5B),
                            size: 26,
                          ),
                        ),
                        const SizedBox(width: 14),
                        const Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                'Scan Shopkeeper QR',
                                style: TextStyle(
                                  fontSize: 15,
                                  fontWeight: FontWeight.bold,
                                  color: Color(0xFF176B5B),
                                ),
                              ),
                              SizedBox(height: 2),
                              Text(
                                'Scan a merchant standee to link with their Udhaar Khata',
                                style: TextStyle(fontSize: 11, color: Colors.black54),
                              ),
                            ],
                          ),
                        ),
                        const Icon(Icons.arrow_forward_ios, size: 14, color: Color(0xFF176B5B)),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 22),

                // My Joined Shops Section
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    const Text(
                      'My Connected Shops',
                      style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800),
                    ),
                    if (!_isLoadingShops)
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                        decoration: BoxDecoration(
                          color: const Color(0xFFE2F1ED),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Text(
                          '${_joinedShops.length} connected',
                          style: const TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.bold,
                            color: Color(0xFF176B5B),
                          ),
                        ),
                      ),
                  ],
                ),
                const SizedBox(height: 10),

                if (_isLoadingShops)
                  const Center(
                    child: Padding(
                      padding: EdgeInsets.all(24),
                      child: CircularProgressIndicator(color: Color(0xFF176B5B)),
                    ),
                  )
                else if (_joinedShops.isEmpty)
                  Container(
                    padding: const EdgeInsets.all(20),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(18),
                      border: Border.all(color: const Color(0xFFE0E5E3)),
                    ),
                    child: Column(
                      children: [
                        const Icon(
                          Icons.storefront_outlined,
                          size: 42,
                          color: Color(0xFF176B5B),
                        ),
                        const SizedBox(height: 12),
                        const Text(
                          'No Shops Connected Yet',
                          style: TextStyle(fontWeight: FontWeight.bold, fontSize: 15),
                        ),
                        const SizedBox(height: 6),
                        const Text(
                          'Scan the Customer Registration QR code displayed at your local store to connect and receive digital receipts.',
                          style: TextStyle(fontSize: 12, color: Colors.black54, height: 1.4),
                          textAlign: TextAlign.center,
                        ),
                        const SizedBox(height: 14),
                        FilledButton.icon(
                          onPressed: _openScanQr,
                          icon: const Icon(Icons.qr_code_scanner, size: 18),
                          label: const Text('Scan QR to Join'),
                          style: FilledButton.styleFrom(
                            backgroundColor: const Color(0xFF176B5B),
                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                          ),
                        ),
                      ],
                    ),
                  )
                else
                  ..._joinedShops.map((shop) => Card(
                        color: Colors.white,
                        elevation: 0,
                        margin: const EdgeInsets.only(bottom: 10),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(16),
                          side: const BorderSide(color: Color(0xFFE0E5E3)),
                        ),
                        child: Padding(
                          padding: const EdgeInsets.all(16),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                children: [
                                  CircleAvatar(
                                    backgroundColor: const Color(0xFFE2F1ED),
                                    child: const Icon(Icons.store, color: Color(0xFF176B5B)),
                                  ),
                                  const SizedBox(width: 12),
                                  Expanded(
                                    child: Column(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: [
                                        Text(
                                          shop.shopName,
                                          style: const TextStyle(
                                            fontWeight: FontWeight.bold,
                                            fontSize: 16,
                                          ),
                                        ),
                                        if (shop.shopAddress.isNotEmpty)
                                          Text(
                                            shop.shopAddress,
                                            style: const TextStyle(
                                              fontSize: 12,
                                              color: Colors.black54,
                                            ),
                                          ),
                                      ],
                                    ),
                                  ),
                                  Container(
                                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                                    decoration: BoxDecoration(
                                      color: const Color(0xFFE2F1ED),
                                      borderRadius: BorderRadius.circular(8),
                                    ),
                                    child: const Text(
                                      'CONNECTED',
                                      style: TextStyle(
                                        fontSize: 10,
                                        fontWeight: FontWeight.w800,
                                        color: Color(0xFF176B5B),
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                              const Divider(height: 20),
                              Row(
                                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                children: [
                                  const Text(
                                    'Initial Balance:',
                                    style: TextStyle(fontSize: 12, color: Colors.black54),
                                  ),
                                  Text(
                                    '₹0.00 DUE',
                                    style: TextStyle(
                                      fontSize: 13,
                                      fontWeight: FontWeight.bold,
                                      color: Colors.green.shade800,
                                    ),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 12),
                              SizedBox(
                                width: double.infinity,
                                child: OutlinedButton.icon(
                                  onPressed: () => _showShopPaymentQrModal(shop),
                                  icon: const Icon(Icons.qr_code_2_rounded, size: 18),
                                  label: const Text('Pay / View Payment QR'),
                                  style: OutlinedButton.styleFrom(
                                    foregroundColor: const Color(0xFF176B5B),
                                    side: const BorderSide(color: Color(0xFF176B5B)),
                                    shape: RoundedRectangleBorder(
                                      borderRadius: BorderRadius.circular(10),
                                    ),
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ),
                      )),

                const SizedBox(height: 20),

                // Active Khata Section (Demo ledger)
                if (linkedStoreCustomer != null) ...[
                  const Text(
                    'Your Active Khata with Shopkeeper',
                    style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800),
                  ),
                  const SizedBox(height: 10),
                  Container(
                    padding: const EdgeInsets.all(18),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(18),
                      border: Border.all(color: const Color(0xFFE0E5E3)),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          'CURRENT OUTSTANDING DUE',
                          style: TextStyle(
                            fontSize: 11,
                            color: Colors.black54,
                            letterSpacing: 0.5,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        const SizedBox(height: 6),
                        Text(
                          money(linkedStoreCustomer.balancePaise),
                          style: TextStyle(
                            fontSize: 28,
                            fontWeight: FontWeight.w900,
                            color: linkedStoreCustomer.balancePaise > 0
                                ? Colors.red.shade700
                                : const Color(0xFF176B5B),
                          ),
                        ),
                        const SizedBox(height: 12),
                        const Divider(color: Color(0xFFF0F3F2)),
                        const SizedBox(height: 8),
                        const Text(
                          'Recent Transactions',
                          style: TextStyle(fontSize: 13, fontWeight: FontWeight.bold),
                        ),
                        const SizedBox(height: 8),
                        if (linkedStoreCustomer.entries.isEmpty)
                          const Text(
                            'No transactions recorded yet.',
                            style: TextStyle(fontSize: 12, color: Colors.black54),
                          )
                        else
                          ...linkedStoreCustomer.entries.take(5).map(
                                (e) => ListTile(
                                  dense: true,
                                  contentPadding: EdgeInsets.zero,
                                  leading: Icon(
                                    e.isCredit ? Icons.arrow_outward : Icons.arrow_downward,
                                    color: e.isCredit ? Colors.deepOrange : Colors.green,
                                    size: 20,
                                  ),
                                  title: Text(e.note, style: const TextStyle(fontSize: 13)),
                                  subtitle: Text(
                                    '${e.createdAt.day}/${e.createdAt.month}/${e.createdAt.year}',
                                    style: const TextStyle(fontSize: 11),
                                  ),
                                  trailing: Text(
                                    '${e.isCredit ? '+' : '-'}${money(e.amountPaise)}',
                                    style: TextStyle(
                                      fontWeight: FontWeight.bold,
                                      fontSize: 13,
                                      color: e.isCredit ? Colors.deepOrange : Colors.green,
                                    ),
                                  ),
                                ),
                              ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 20),
                ],

                // Logout / Switch Role
                OutlinedButton.icon(
                  onPressed: () => _onLogout(context),
                  icon: const Icon(Icons.logout),
                  label: const Text('Log Out / Switch Role'),
                  style: OutlinedButton.styleFrom(
                    foregroundColor: const Color(0xFF176B5B),
                    side: const BorderSide(color: Color(0xFF176B5B)),
                    padding: const EdgeInsets.symmetric(vertical: 14),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                  ),
                ),
                const SizedBox(height: 16),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
