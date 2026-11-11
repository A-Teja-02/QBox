import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';
import 'package:qr_flutter/qr_flutter.dart';
import '../main.dart';
import '../models/profiles.dart';
import '../services/api_service.dart';
import 'shopkeeper_login_screen.dart';

/// Screen for Shopkeepers to view, print, rotate, or revoke their static Customer Registration QR code.
/// Also displays the list of onboarded customers for this shop.
class ShopQrManagementScreen extends StatefulWidget {
  const ShopQrManagementScreen({
    super.key,
    required this.store,
    this.apiService,
  });

  final QboxStore store;
  final ApiService? apiService;

  @override
  State<ShopQrManagementScreen> createState() => _ShopQrManagementScreenState();
}

class _ShopQrManagementScreenState extends State<ShopQrManagementScreen> {
  late final ApiService _apiService = widget.apiService ?? ApiService();

  ShopRegistrationQrData? _qrData;
  List<ShopCustomerItem> _registeredCustomers = [];
  bool _isLoading = true;
  String? _errorMessage;

  ShopPaymentQrMeta? _paymentQrMeta;
  Uint8List? _paymentQrBytes;
  bool _isLoadingPaymentQr = false;

  @override
  void initState() {
    super.initState();
    _loadQrAndCustomers();
  }

  Future<void> _loadQrAndCustomers() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    final shopId = widget.store.shopkeeperProfile?.shopId ?? 'me';
    var token = widget.store.accessToken;

    if (widget.store.isDemoSession) {
      setState(() {
        _errorMessage = 'Offline Demo Mode: Registration QR management requires an authenticated shopkeeper account. Please log in with a live account.';
        _isLoading = false;
      });
      return;
    }

    if (token == null || token.isEmpty) {
      if (widget.apiService != null) {
        // Injected test service simulating token rejection
        final res = await _apiService.getShopRegistrationQr(shopId, authToken: '');
        if (!mounted) return;
        setState(() {
          _errorMessage = res.errorMessage ?? 'Invalid or expired authentication token.';
          _isLoading = false;
        });
        return;
      }

      setState(() {
        _errorMessage = 'Invalid or expired authentication token. Please log in as a shopkeeper to view your QR code.';
        _isLoading = false;
      });
      return;
    }

    var qrResult = await _apiService.getShopRegistrationQr(shopId, authToken: token);

    // If token is invalid or expired, attempt seamless refresh using refresh token
    if (!qrResult.isSuccess &&
        _isAuthErrorMsg(qrResult.errorMessage) &&
        widget.store.refreshToken != null &&
        widget.store.refreshToken!.isNotEmpty) {
      final refreshRes = await _apiService.refreshAccessToken(widget.store.refreshToken!);
      if (refreshRes.isSuccess && refreshRes.data != null) {
        final newAccess = refreshRes.data!['access_token'] as String;
        final newRefresh = refreshRes.data!['refresh_token'] as String?;
        widget.store.updateTokens(newAccess, newRefreshToken: newRefresh);
        token = newAccess;
        qrResult = await _apiService.getShopRegistrationQr(shopId, authToken: token);
      }
    }

    final custResult = await _apiService.getShopCustomers(shopId, authToken: token);

    if (!mounted) return;

    if (qrResult.isSuccess && qrResult.data != null) {
      setState(() {
        _qrData = qrResult.data;
        _registeredCustomers = custResult.isSuccess ? (custResult.data ?? []) : [];
        _isLoading = false;
      });
      _loadPaymentQr(token, shopId);
    } else {
      setState(() {
        _errorMessage = qrResult.errorMessage ?? 'Failed to load shop QR';
        _isLoading = false;
      });
    }
  }

  Future<void> _loadPaymentQr(String token, String shopId) async {
    setState(() => _isLoadingPaymentQr = true);
    final res = await _apiService.getShopPaymentQrMeta(shopId, authToken: token);
    if (!mounted) return;
    if (res.isSuccess) {
      setState(() {
        _paymentQrMeta = res.data;
        _isLoadingPaymentQr = false;
      });
      if (res.data != null && res.data!.imageUrl.isNotEmpty) {
        final imgRes = await _apiService.downloadPaymentQrImage(
          url: res.data!.imageUrl,
          authToken: token,
        );
        if (mounted && imgRes.isSuccess && imgRes.data != null) {
          setState(() => _paymentQrBytes = imgRes.data);
        }
      }
    } else {
      setState(() => _isLoadingPaymentQr = false);
    }
  }

  Future<void> _pickAndUploadPaymentQr() async {
    try {
      final picker = ImagePicker();
      final picked = await picker.pickImage(source: ImageSource.gallery);
      if (picked == null) return;

      final filename = picked.name.toLowerCase();
      final isAllowed = filename.endsWith('.png') ||
          filename.endsWith('.jpg') ||
          filename.endsWith('.jpeg');
      if (!isAllowed) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            backgroundColor: Colors.red,
            content: Text('Invalid image format. Only PNG, JPG, and JPEG images are allowed.'),
          ),
        );
        return;
      }

      final bytes = await picked.readAsBytes();
      if (bytes.length > 5 * 1024 * 1024) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            backgroundColor: Colors.red,
            content: Text('File size exceeds 5 MB limit. Please select a smaller QR code image.'),
          ),
        );
        return;
      }

      final shopId = widget.store.shopkeeperProfile?.shopId ?? 'me';
      final token = widget.store.accessToken;
      if (token == null) return;
      setState(() => _isLoadingPaymentQr = true);

      final res = await _apiService.updateShopPaymentQr(
        shopId,
        authToken: token,
        filePath: picked.path,
        fileBytes: bytes,
        fileName: picked.name,
      );

      if (!mounted) return;
      if (res.isSuccess && res.data != null) {
        setState(() {
          _paymentQrMeta = res.data;
          _paymentQrBytes = bytes;
          _isLoadingPaymentQr = false;
        });
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            backgroundColor: Color(0xFF176B5B),
            content: Text('Payment QR code updated successfully!'),
          ),
        );
      } else {
        setState(() => _isLoadingPaymentQr = false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            backgroundColor: Colors.red,
            content: Text(res.errorMessage ?? 'Failed to upload payment QR.'),
          ),
        );
      }
    } on MissingPluginException catch (_) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Image picker not available in test environment.')),
      );
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(backgroundColor: Colors.red, content: Text('Error: $e')),
        );
      }
    }
  }

  Future<void> _confirmRemovePaymentQr() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Remove Payment QR?'),
        content: const Text(
          'Are you sure you want to remove your store UPI payment QR code? '
          'Connected customers will not be able to view your payment QR until you upload a new one.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: Colors.red.shade700),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Remove QR'),
          ),
        ],
      ),
    );

    if (confirmed == true && mounted) {
      final shopId = widget.store.shopkeeperProfile?.shopId ?? 'me';
      final token = widget.store.accessToken;
      if (token == null) return;
      setState(() => _isLoadingPaymentQr = true);

      final res = await _apiService.deleteShopPaymentQr(shopId, authToken: token);
      if (!mounted) return;
      if (res.isSuccess) {
        setState(() {
          _paymentQrMeta = null;
          _paymentQrBytes = null;
          _isLoadingPaymentQr = false;
        });
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            backgroundColor: Color(0xFF176B5B),
            content: Text('Payment QR code removed successfully.'),
          ),
        );
      } else {
        setState(() => _isLoadingPaymentQr = false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            backgroundColor: Colors.red,
            content: Text(res.errorMessage ?? 'Failed to remove payment QR.'),
          ),
        );
      }
    }
  }

  static bool _isAuthErrorMsg(String? error) {
    if (error == null) return false;
    final lower = error.toLowerCase();
    return lower.contains('token') ||
        lower.contains('unauthorized') ||
        lower.contains('expired') ||
        lower.contains('log in') ||
        lower.contains('authenticate');
  }

  Future<void> _confirmRotateQr() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Rotate Registration QR?'),
        content: const Text(
          'Rotating this QR code will instantly deactivate your existing QR.\n\n'
          '⚠️ Any existing printed QR codes in your shop will stop working immediately. '
          'You will need to print and display the new QR code.\n\n'
          'Are you sure you want to proceed?',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: Colors.amber.shade900),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Rotate QR'),
          ),
        ],
      ),
    );

    if (confirmed == true && mounted) {
      if (widget.store.isDemoSession || widget.store.accessToken == null || widget.store.accessToken!.isEmpty) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            backgroundColor: Colors.orange,
            content: Text('Cannot rotate QR in offline demo mode. Please log in with a live account.'),
            behavior: SnackBarBehavior.floating,
          ),
        );
        return;
      }
      setState(() => _isLoading = true);
      final shopId = widget.store.shopkeeperProfile?.shopId ?? 'me';
      var token = widget.store.accessToken!;

      var res = await _apiService.rotateShopRegistrationQr(shopId, authToken: token);

      if (!res.isSuccess &&
          _isAuthErrorMsg(res.errorMessage) &&
          widget.store.refreshToken != null &&
          widget.store.refreshToken!.isNotEmpty) {
        final refreshRes = await _apiService.refreshAccessToken(widget.store.refreshToken!);
        if (refreshRes.isSuccess && refreshRes.data != null) {
          final newAccess = refreshRes.data!['access_token'] as String;
          final newRefresh = refreshRes.data!['refresh_token'] as String?;
          widget.store.updateTokens(newAccess, newRefreshToken: newRefresh);
          token = newAccess;
          res = await _apiService.rotateShopRegistrationQr(shopId, authToken: token);
        }
      }

      if (!mounted) return;

      if (res.isSuccess && res.data != null) {
        setState(() {
          _qrData = res.data;
          _isLoading = false;
        });
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            backgroundColor: Color(0xFF176B5B),
            content: Text('Registration QR rotated successfully. Old QR deactivated.'),
            behavior: SnackBarBehavior.floating,
          ),
        );
      } else {
        setState(() => _isLoading = false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            backgroundColor: Colors.red.shade800,
            content: Text(res.errorMessage ?? 'Failed to rotate QR'),
            behavior: SnackBarBehavior.floating,
          ),
        );
      }
    }
  }

  Future<void> _confirmRevokeQr() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Revoke Registration QR?'),
        content: const Text(
          'Revoking will immediately deactivate customer onboarding for your shop.\n\n'
          'Customers will not be able to join via QR until you rotate/generate a new one.\n\n'
          'Are you sure you want to revoke this QR?',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: Colors.red.shade700),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Revoke QR'),
          ),
        ],
      ),
    );

    if (confirmed == true && mounted) {
      if (widget.store.isDemoSession || widget.store.accessToken == null || widget.store.accessToken!.isEmpty) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            backgroundColor: Colors.orange,
            content: Text('Cannot rotate QR in offline demo mode. Please log in with a live account.'),
            behavior: SnackBarBehavior.floating,
          ),
        );
        return;
      }
      setState(() => _isLoading = true);
      final shopId = widget.store.shopkeeperProfile?.shopId ?? 'me';
      var token = widget.store.accessToken!;

      var res = await _apiService.revokeShopRegistrationQr(shopId, authToken: token);

      if (!res.isSuccess &&
          _isAuthErrorMsg(res.errorMessage) &&
          widget.store.refreshToken != null &&
          widget.store.refreshToken!.isNotEmpty) {
        final refreshRes = await _apiService.refreshAccessToken(widget.store.refreshToken!);
        if (refreshRes.isSuccess && refreshRes.data != null) {
          final newAccess = refreshRes.data!['access_token'] as String;
          final newRefresh = refreshRes.data!['refresh_token'] as String?;
          widget.store.updateTokens(newAccess, newRefreshToken: newRefresh);
          token = newAccess;
          res = await _apiService.revokeShopRegistrationQr(shopId, authToken: token);
        }
      }

      if (!mounted) return;

      if (res.isSuccess) {
        await _loadQrAndCustomers();
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            backgroundColor: Colors.orange,
            content: Text('Registration QR code revoked.'),
            behavior: SnackBarBehavior.floating,
          ),
        );
      } else {
        setState(() => _isLoading = false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            backgroundColor: Colors.red.shade800,
            content: Text(res.errorMessage ?? 'Failed to revoke QR'),
            behavior: SnackBarBehavior.floating,
          ),
        );
      }
    }
  }

  void _copyRegistrationUrl() {
    if (_qrData == null) return;
    Clipboard.setData(ClipboardData(text: _qrData!.registrationUrl));
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Registration link copied to clipboard!'),
        behavior: SnackBarBehavior.floating,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final shopName = widget.store.shopkeeperProfile?.shopName ?? 'My Shop';
    final shopAddress = widget.store.shopkeeperProfile?.shopAddress ?? '';

    return DefaultTabController(
      length: 2,
      child: Scaffold(
        backgroundColor: const Color(0xFFF6F8F7),
        appBar: AppBar(
          title: const Text(
            'Shop QR Management',
            style: TextStyle(fontWeight: FontWeight.bold),
          ),
          backgroundColor: Colors.white,
          elevation: 0,
          foregroundColor: Colors.black87,
          bottom: const TabBar(
            labelColor: Color(0xFF176B5B),
            indicatorColor: Color(0xFF176B5B),
            unselectedLabelColor: Colors.black54,
            tabs: [
              Tab(icon: Icon(Icons.person_add_alt_1), text: 'Registration QR'),
              Tab(icon: Icon(Icons.qr_code_2), text: 'Store Payment QR'),
            ],
          ),
          actions: [
            IconButton(
              icon: const Icon(Icons.refresh_rounded),
              tooltip: 'Refresh',
              onPressed: _loadQrAndCustomers,
            ),
          ],
        ),
        body: SafeArea(
          child: _isLoading
              ? const Center(child: CircularProgressIndicator(color: Color(0xFF176B5B)))
              : _errorMessage != null
                  ? Center(
                      child: Padding(
                        padding: const EdgeInsets.all(24),
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Icon(
                              _isAuthErrorMsg(_errorMessage) ? Icons.lock_outline : Icons.error_outline,
                              size: 48,
                              color: _isAuthErrorMsg(_errorMessage) ? const Color(0xFF176B5B) : Colors.red.shade400,
                            ),
                            const SizedBox(height: 12),
                            Text(
                              _errorMessage!,
                              textAlign: TextAlign.center,
                              style: const TextStyle(fontSize: 14, height: 1.4),
                            ),
                            const SizedBox(height: 20),
                            if (_isAuthErrorMsg(_errorMessage)) ...[
                              FilledButton.icon(
                                style: FilledButton.styleFrom(
                                  backgroundColor: const Color(0xFF176B5B),
                                  padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
                                ),
                                onPressed: () {
                                  Navigator.push(
                                    context,
                                    MaterialPageRoute(
                                      builder: (_) => ShopkeeperLoginScreen(store: widget.store),
                                    ),
                                  );
                                },
                                icon: const Icon(Icons.login),
                                label: const Text('Log In as Shopkeeper'),
                              ),
                              const SizedBox(height: 8),
                              TextButton.icon(
                                onPressed: _loadQrAndCustomers,
                                icon: const Icon(Icons.refresh, size: 18),
                                label: const Text('Retry'),
                              ),
                            ] else
                              FilledButton.icon(
                                onPressed: _loadQrAndCustomers,
                                icon: const Icon(Icons.refresh),
                                label: const Text('Try Again'),
                              ),
                          ],
                        ),
                      ),
                    )
                  : TabBarView(
                      children: [
                        _buildRegistrationTab(shopName, shopAddress),
                        _buildPaymentQrTab(),
                      ],
                    ),
        ),
      ),
    );
  }

  Widget _buildRegistrationTab(String shopName, String shopAddress) {
    return ListView(
                    padding: const EdgeInsets.all(18),
                    children: [
                      // Header Notice Banner
                      Container(
                        padding: const EdgeInsets.all(14),
                        decoration: BoxDecoration(
                          color: const Color(0xFFE2F1ED),
                          borderRadius: BorderRadius.circular(16),
                          border: Border.all(color: const Color(0xFFBCE3D7)),
                        ),
                        child: const Row(
                          children: [
                            Icon(Icons.info_outline, color: Color(0xFF176B5B), size: 22),
                            SizedBox(width: 10),
                            Expanded(
                              child: Text(
                                'This permanent static QR allows customers to find your shop and join your Udhaar khata. It is NOT a payment QR.',
                                style: TextStyle(
                                  fontSize: 12,
                                  color: Color(0xFF0F4B3F),
                                  fontWeight: FontWeight.w500,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 18),

                      // QR Presentation Card
                      Container(
                        padding: const EdgeInsets.all(20),
                        decoration: BoxDecoration(
                          color: Colors.white,
                          borderRadius: BorderRadius.circular(22),
                          border: Border.all(
                            color: _qrData?.isActive == true ? const Color(0xFF176B5B) : Colors.red.shade300,
                            width: 1.5,
                          ),
                          boxShadow: [
                            BoxShadow(
                              color: Colors.black.withValues(alpha: 0.05),
                              blurRadius: 16,
                              offset: const Offset(0, 6),
                            ),
                          ],
                        ),
                        child: Column(
                          children: [
                            // Status Badge
                            Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                Row(
                                  children: [
                                    Icon(
                                      _qrData?.isActive == true ? Icons.verified : Icons.cancel_outlined,
                                      color: _qrData?.isActive == true ? const Color(0xFF176B5B) : Colors.red,
                                      size: 18,
                                    ),
                                    const SizedBox(width: 6),
                                    Text(
                                      _qrData?.isActive == true ? 'ACTIVE REGISTRATION QR' : 'REVOKED',
                                      style: TextStyle(
                                        fontSize: 11,
                                        fontWeight: FontWeight.w800,
                                        letterSpacing: 0.8,
                                        color: _qrData?.isActive == true ? const Color(0xFF176B5B) : Colors.red,
                                      ),
                                    ),
                                  ],
                                ),
                                Container(
                                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                                  decoration: BoxDecoration(
                                    color: const Color(0xFFE2F1ED),
                                    borderRadius: BorderRadius.circular(8),
                                  ),
                                  child: const Text(
                                    'STATIC',
                                    style: TextStyle(
                                      fontSize: 10,
                                      fontWeight: FontWeight.bold,
                                      color: Color(0xFF176B5B),
                                    ),
                                  ),
                                ),
                              ],
                            ),
                            const Divider(height: 24),

                            // QR Image View
                            if (_qrData?.isActive == true && _qrData!.registrationUrl.isNotEmpty) ...[
                              Container(
                                padding: const EdgeInsets.all(16),
                                decoration: BoxDecoration(
                                  color: Colors.white,
                                  borderRadius: BorderRadius.circular(16),
                                  border: Border.all(color: Colors.black12),
                                ),
                                child: QrImageView(
                                  data: _qrData!.registrationUrl,
                                  version: QrVersions.auto,
                                  size: 210.0,
                                  gapless: true,
                                  errorStateBuilder: (cxt, err) {
                                    return const Center(
                                      child: Text(
                                        'Error rendering QR code',
                                        textAlign: TextAlign.center,
                                      ),
                                    );
                                  },
                                ),
                              ),
                              const SizedBox(height: 14),
                              Text(
                                shopName,
                                style: const TextStyle(
                                  fontSize: 18,
                                  fontWeight: FontWeight.bold,
                                  color: Colors.black87,
                                ),
                                textAlign: TextAlign.center,
                              ),
                              if (shopAddress.isNotEmpty) ...[
                                const SizedBox(height: 4),
                                Text(
                                  shopAddress,
                                  style: const TextStyle(fontSize: 12, color: Colors.black54),
                                  textAlign: TextAlign.center,
                                ),
                              ],
                              const SizedBox(height: 12),
                              // Registration link container
                              InkWell(
                                onTap: _copyRegistrationUrl,
                                borderRadius: BorderRadius.circular(10),
                                child: Container(
                                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                                  decoration: BoxDecoration(
                                    color: const Color(0xFFF6F8F7),
                                    borderRadius: BorderRadius.circular(10),
                                    border: Border.all(color: Colors.black12),
                                  ),
                                  child: Row(
                                    children: [
                                      const Icon(Icons.link, size: 16, color: Color(0xFF176B5B)),
                                      const SizedBox(width: 8),
                                      Expanded(
                                        child: Text(
                                          _qrData!.registrationUrl,
                                          style: const TextStyle(
                                            fontSize: 12,
                                            fontFamily: 'monospace',
                                            color: Colors.black87,
                                          ),
                                          overflow: TextOverflow.ellipsis,
                                        ),
                                      ),
                                      const Icon(Icons.copy, size: 16, color: Colors.black54),
                                    ],
                                  ),
                                ),
                              ),
                            ] else ...[
                              Container(
                                padding: const EdgeInsets.all(32),
                                alignment: Alignment.center,
                                child: Column(
                                  children: [
                                    Icon(Icons.qr_code_scanner, size: 64, color: Colors.grey.shade400),
                                    const SizedBox(height: 12),
                                    const Text(
                                      'This QR has been revoked.',
                                      style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
                                    ),
                                    const SizedBox(height: 6),
                                    const Text(
                                      'Rotate to create a fresh active customer onboarding QR for this shop.',
                                      style: TextStyle(fontSize: 12, color: Colors.black54),
                                      textAlign: TextAlign.center,
                                    ),
                                  ],
                                ),
                              ),
                            ],

                            const SizedBox(height: 20),

                            // Action Buttons
                            Row(
                              children: [
                                Expanded(
                                  child: OutlinedButton.icon(
                                    onPressed: _copyRegistrationUrl,
                                    icon: const Icon(Icons.share_outlined, size: 16),
                                    label: const Text('Share URL'),
                                    style: OutlinedButton.styleFrom(
                                      foregroundColor: const Color(0xFF176B5B),
                                      side: const BorderSide(color: Color(0xFF176B5B)),
                                      padding: const EdgeInsets.symmetric(vertical: 12),
                                    ),
                                  ),
                                ),
                                const SizedBox(width: 10),
                                Expanded(
                                  child: OutlinedButton.icon(
                                    onPressed: _confirmRotateQr,
                                    icon: const Icon(Icons.rotate_right_rounded, size: 16),
                                    label: const Text('Rotate QR'),
                                    style: OutlinedButton.styleFrom(
                                      foregroundColor: Colors.amber.shade900,
                                      side: BorderSide(color: Colors.amber.shade700),
                                      padding: const EdgeInsets.symmetric(vertical: 12),
                                    ),
                                  ),
                                ),
                                if (_qrData?.isActive == true) ...[
                                  const SizedBox(width: 10),
                                  IconButton(
                                    icon: const Icon(Icons.delete_outline, color: Colors.red),
                                    tooltip: 'Revoke QR',
                                    onPressed: _confirmRevokeQr,
                                  ),
                                ],
                              ],
                            ),
                          ],
                        ),
                      ),

                      const SizedBox(height: 24),

                      // Registered Customers Section
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          const Text(
                            'Customers Joined via QR',
                            style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                          ),
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                            decoration: BoxDecoration(
                              color: const Color(0xFFE2F1ED),
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: Text(
                              '${_registeredCustomers.length} joined',
                              style: const TextStyle(
                                fontSize: 12,
                                fontWeight: FontWeight.bold,
                                color: Color(0xFF176B5B),
                              ),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 10),

                      if (_registeredCustomers.isEmpty) ...[
                        Card(
                          color: Colors.white,
                          elevation: 0,
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                          child: const Padding(
                            padding: EdgeInsets.all(24),
                            child: Column(
                              children: [
                                Icon(Icons.group_outlined, size: 40, color: Colors.black26),
                                SizedBox(height: 8),
                                Text(
                                  'No customers joined via QR yet',
                                  style: TextStyle(fontWeight: FontWeight.bold, color: Colors.black54),
                                ),
                                SizedBox(height: 4),
                                Text(
                                  'Print and display your QR in your shop. When customers scan it, they will appear here.',
                                  style: TextStyle(fontSize: 11, color: Colors.black38),
                                  textAlign: TextAlign.center,
                                ),
                              ],
                            ),
                          ),
                        ),
                      ] else ...[
                        ..._registeredCustomers.map((cust) => Card(
                              color: Colors.white,
                              elevation: 0,
                              margin: const EdgeInsets.only(bottom: 8),
                              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                              child: ListTile(
                                leading: CircleAvatar(
                                  backgroundColor: const Color(0xFFE2F1ED),
                                  child: Text(
                                    cust.fullName.isNotEmpty ? cust.fullName[0].toUpperCase() : 'C',
                                    style: const TextStyle(
                                      color: Color(0xFF176B5B),
                                      fontWeight: FontWeight.bold,
                                    ),
                                  ),
                                ),
                                title: Text(cust.fullName, style: const TextStyle(fontWeight: FontWeight.w600)),
                                subtitle: Text(cust.phone),
                                trailing: Container(
                                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                                  decoration: BoxDecoration(
                                    color: const Color(0xFFE2F1ED),
                                    borderRadius: BorderRadius.circular(8),
                                  ),
                                  child: const Text(
                                    '₹0.00 DUE',
                                    style: TextStyle(
                                      fontSize: 11,
                                      fontWeight: FontWeight.bold,
                                      color: Color(0xFF176B5B),
                                    ),
                                  ),
                                ),
                              ),
                            )),
                      ],
                    ],
                  );
  }

  Widget _buildPaymentQrTab() {
    if (_isLoadingPaymentQr) {
      return const Center(child: CircularProgressIndicator(color: Color(0xFF176B5B)));
    }

    return ListView(
      padding: const EdgeInsets.all(18),
      children: [
        // Information Banner
        Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: const Color(0xFFE2F1ED),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: const Color(0xFFBCE3D7)),
          ),
          child: const Row(
            children: [
              Icon(Icons.info_outline, color: Color(0xFF176B5B), size: 22),
              SizedBox(width: 10),
              Expanded(
                child: Text(
                  'Your store UPI payment QR standee is displayed to connected customers so they can pay repayments directly from GPay, PhonePe, Paytm, or BHIM.',
                  style: TextStyle(
                    fontSize: 12,
                    color: Color(0xFF0F4B3F),
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 18),

        if (_paymentQrMeta == null || !_paymentQrMeta!.isActive) ...[
          // Empty State: Prompt to upload
          Container(
            padding: const EdgeInsets.all(28),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(22),
              border: Border.all(color: const Color(0xFFE0E5E3)),
            ),
            child: Column(
              children: [
                const Icon(
                  Icons.qr_code_scanner,
                  size: 54,
                  color: Color(0xFF176B5B),
                ),
                const SizedBox(height: 14),
                const Text(
                  'No Payment QR Uploaded',
                  style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
                ),
                const SizedBox(height: 6),
                const Text(
                  'Upload your shop static UPI QR standee (PhonePe, Google Pay, Paytm, BHIM, Bank QR) so customers can view it and make repayments.',
                  style: TextStyle(fontSize: 12, color: Colors.black54, height: 1.4),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 20),
                FilledButton.icon(
                  onPressed: _pickAndUploadPaymentQr,
                  icon: const Icon(Icons.photo_library_outlined, size: 20),
                  label: const Text('Upload from Gallery'),
                  style: FilledButton.styleFrom(
                    backgroundColor: const Color(0xFF176B5B),
                    padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                  ),
                ),
              ],
            ),
          ),
        ] else ...[
          // Active Payment QR Presentation Card
          Container(
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(22),
              border: Border.all(color: const Color(0xFF176B5B), width: 1.5),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.05),
                  blurRadius: 16,
                  offset: const Offset(0, 6),
                ),
              ],
            ),
            child: Column(
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    const Row(
                      children: [
                        Icon(Icons.verified, color: Color(0xFF176B5B), size: 18),
                        SizedBox(width: 6),
                        Text(
                          'ACTIVE PAYMENT QR',
                          style: TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.w800,
                            letterSpacing: 0.8,
                            color: Color(0xFF176B5B),
                          ),
                        ),
                      ],
                    ),
                    if (_paymentQrMeta!.upiProvider != null && _paymentQrMeta!.upiProvider!.isNotEmpty)
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                        decoration: BoxDecoration(
                          color: const Color(0xFFE2F1ED),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Text(
                          '${_paymentQrMeta!.upiProvider} UPI',
                          style: const TextStyle(
                            fontSize: 10,
                            fontWeight: FontWeight.bold,
                            color: Color(0xFF176B5B),
                          ),
                        ),
                      ),
                  ],
                ),
                const SizedBox(height: 16),

                // Image Preview Box
                Container(
                  width: 220,
                  height: 220,
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(16),
                    border: Border.all(color: Colors.black12),
                  ),
                  alignment: Alignment.center,
                  child: _paymentQrBytes != null
                      ? ClipRRect(
                          borderRadius: BorderRadius.circular(12),
                          child: Image.memory(
                            _paymentQrBytes!,
                            width: 210,
                            height: 210,
                            fit: BoxFit.contain,
                          ),
                        )
                      : const Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            CircularProgressIndicator(strokeWidth: 2, color: Color(0xFF176B5B)),
                            SizedBox(height: 8),
                            Text('Loading QR image...', style: TextStyle(fontSize: 11, color: Colors.black54)),
                          ],
                        ),
                ),
                const SizedBox(height: 12),

                Text(
                  _paymentQrMeta!.originalFilename,
                  style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 2),
                Text(
                  '${(_paymentQrMeta!.fileSizeBytes / 1024).toStringAsFixed(1)} KB • ${_paymentQrMeta!.contentType}',
                  style: const TextStyle(fontSize: 11, color: Colors.black54),
                ),
                const SizedBox(height: 16),

                // Action buttons: Replace & Remove
                Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    OutlinedButton.icon(
                      onPressed: _pickAndUploadPaymentQr,
                      icon: const Icon(Icons.refresh, size: 16),
                      label: const Text('Replace QR'),
                      style: OutlinedButton.styleFrom(
                        foregroundColor: const Color(0xFF176B5B),
                        side: const BorderSide(color: Color(0xFF176B5B)),
                      ),
                    ),
                    const SizedBox(width: 14),
                    TextButton.icon(
                      onPressed: _confirmRemovePaymentQr,
                      icon: const Icon(Icons.delete_outline, size: 16, color: Colors.red),
                      label: const Text('Remove', style: TextStyle(color: Colors.red)),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],

        const SizedBox(height: 20),

        // Non-custodial Merchant Notice
        Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: const Color(0xFFFFF8E1),
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: const Color(0xFFFFE082)),
          ),
          child: const Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(Icons.security_outlined, color: Color(0xFFF57F17), size: 20),
              SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Non-Custodial Direct Payments',
                      style: TextStyle(
                        fontWeight: FontWeight.bold,
                        fontSize: 12,
                        color: Color(0xFFE65100),
                      ),
                    ),
                    SizedBox(height: 3),
                    Text(
                      'Qbox never holds customer funds. Customer payments land directly in your bank account linked to your UPI QR. After receiving payment in your UPI app, record it in your Udhaar Khata ledger.',
                      style: TextStyle(fontSize: 11, color: Color(0xFF5D4037), height: 1.3),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

