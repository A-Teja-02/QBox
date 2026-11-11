import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';
import '../main.dart';
import '../models/profiles.dart';
import '../services/api_service.dart';
import '../services/deep_link_service.dart';
import '../services/token_storage_service.dart';
import 'customer_home_screen.dart';
import 'customer_login_screen.dart';
import 'customer_signup_screen.dart';

/// Customer screen to scan or enter a shop registration QR token/URL,
/// inspect verified shop details, and confirm joining the shop's Udhaar directory.
///
/// Features:
/// - Real camera scanner via [MobileScanner] with runtime permission handling.
/// - Live viewfinder, torch toggle, and camera flip controls.
/// - Fallback manual token/link entry.
/// - Secure persistence of pending invitation tokens across customer signup/login.
/// - Explicit customer confirmation dialog ("Do you want to connect your Qbox account with [Shop Name]?")
/// - Idempotent backend shop connection with zero initial Udhaar balance and no ledger transaction.
class ScanShopQrScreen extends StatefulWidget {
  const ScanShopQrScreen({
    super.key,
    required this.store,
    this.initialToken,
  });

  final QboxStore store;
  final String? initialToken;

  @override
  State<ScanShopQrScreen> createState() => _ScanShopQrScreenState();
}

class _ScanShopQrScreenState extends State<ScanShopQrScreen> {
  final _apiService = ApiService();
  final _tokenController = TextEditingController();

  MobileScannerController? _scannerController;
  bool _isCameraInitialized = false;
  bool _isTorchOn = false;
  bool _isCameraPermissionDenied = false;

  PublicShopInfo? _verifiedShop;
  bool _isResolving = false;
  bool _isJoining = false;
  String? _lookupError;

  @override
  void initState() {
    super.initState();
    final effectiveToken = widget.initialToken ?? widget.store.pendingShopToken;

    if (effectiveToken != null && effectiveToken.isNotEmpty) {
      _tokenController.text = effectiveToken;
      widget.store.setPendingShopToken(effectiveToken);
      _resolveToken(effectiveToken);
    } else {
      _initScanner();
    }
  }

  void _initScanner() {
    if (TokenStorageService.isTestEnvironment) {
      // In automated test environments, avoid initializing native camera
      return;
    }

    try {
      _scannerController = MobileScannerController(
        detectionSpeed: DetectionSpeed.noDuplicates,
        returnImage: false,
        torchEnabled: false,
      );
      _isCameraInitialized = true;
    } catch (e) {
      _lookupError = 'Could not initialize camera: $e';
    }
  }

  @override
  void dispose() {
    _tokenController.dispose();
    _scannerController?.dispose();
    super.dispose();
  }

  void _onBarcodeDetected(BarcodeCapture capture) {
    if (_isResolving || _verifiedShop != null) return;

    final barcode = capture.barcodes.firstOrNull;
    final rawValue = barcode?.rawValue;
    if (rawValue == null || rawValue.trim().isEmpty) return;

    final token = DeepLinkService.extractToken(rawValue.trim());
    if (token != null && token.isNotEmpty) {
      _scannerController?.stop();
      _tokenController.text = token;
      widget.store.setPendingShopToken(token);
      _resolveToken(token);
    } else {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Unrecognized QR code. Please scan a Qbox shop registration QR.'),
            duration: Duration(seconds: 2),
            behavior: SnackBarBehavior.floating,
          ),
        );
      }
    }
  }

  Future<void> _toggleTorch() async {
    if (_scannerController == null) return;
    try {
      await _scannerController!.toggleTorch();
      if (mounted) {
        setState(() => _isTorchOn = !_isTorchOn);
      }
    } catch (_) {}
  }

  Future<void> _switchCamera() async {
    if (_scannerController == null) return;
    try {
      await _scannerController!.switchCamera();
    } catch (_) {}
  }

  Future<void> _resolveToken(String rawToken) async {
    final trimmed = rawToken.trim();
    if (trimmed.isEmpty) {
      setState(() => _lookupError = 'Please enter or scan a valid QR registration link or token');
      return;
    }

    setState(() {
      _isResolving = true;
      _lookupError = null;
      _verifiedShop = null;
    });

    final res = await _apiService.lookupPublicShop(trimmed);
    if (!mounted) return;

    if (res.isSuccess && res.data != null) {
      setState(() {
        _verifiedShop = res.data;
        _isResolving = false;
      });
      // Preserve verified shop and pending token in store
      widget.store.setPendingShopToken(trimmed, shopInfo: res.data);
    } else {
      setState(() {
        _lookupError = res.errorMessage ?? 'Invalid or inactive shop QR code';
        _isResolving = false;
      });
    }
  }

  Future<void> _confirmJoinShop() async {
    if (_verifiedShop == null) return;

    final token = widget.store.accessToken;
    if (token == null || token.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          backgroundColor: Colors.orange,
          content: Text('Please log in with a customer account to join this shop.'),
          behavior: SnackBarBehavior.floating,
        ),
      );
      return;
    }

    setState(() => _isJoining = true);

    final result = await _apiService.joinShop(
      shopId: _verifiedShop!.shopId,
      token: _verifiedShop!.token,
      authToken: token,
    );

    if (!mounted) return;
    setState(() => _isJoining = false);

    if (result.isSuccess) {
      // Clear pending token now that shop join is complete
      await widget.store.clearPendingShopToken();

      final status = result.data?['status'] as String?;
      final isAlreadyJoined = status == 'already_joined';

      await showDialog(
        context: context,
        barrierDismissible: false,
        builder: (ctx) => AlertDialog(
          icon: Icon(
            isAlreadyJoined ? Icons.info_outline : Icons.check_circle,
            color: const Color(0xFF176B5B),
            size: 48,
          ),
          title: Text(isAlreadyJoined ? 'Already Connected' : 'Successfully Joined!'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                isAlreadyJoined
                    ? 'You are already connected to ${_verifiedShop!.shopName}.'
                    : 'You are now connected to ${_verifiedShop!.shopName}.',
                textAlign: TextAlign.center,
                style: const TextStyle(fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 12),
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: const Color(0xFFE2F1ED),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: const Text(
                  '✅ Initial balance: ₹0.00\n'
                  'Zero Udhaar debt or payment is created upon joining.',
                  textAlign: TextAlign.center,
                  style: TextStyle(fontSize: 12, color: Color(0xFF0F4B3F), height: 1.4),
                ),
              ),
            ],
          ),
          actions: [
            FilledButton(
              style: FilledButton.styleFrom(backgroundColor: const Color(0xFF176B5B)),
              onPressed: () {
                Navigator.pop(ctx);
                if (widget.store.customerProfile != null) {
                  Navigator.pushAndRemoveUntil(
                    context,
                    MaterialPageRoute(
                      builder: (_) => CustomerHomeScreen(
                        customer: widget.store.customerProfile!,
                        store: widget.store,
                      ),
                    ),
                    (route) => false,
                  );
                } else {
                  Navigator.pop(context);
                }
              },
              child: const Text('Go to Customer Home'),
            ),
          ],
        ),
      );
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          backgroundColor: Colors.red.shade800,
          content: Text(result.errorMessage ?? 'Failed to join shop'),
          behavior: SnackBarBehavior.floating,
        ),
      );
    }
  }

  void _onCancelJoin() {
    widget.store.clearPendingShopToken();
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Shop connection cancelled. You can scan or join another shop anytime.'),
        behavior: SnackBarBehavior.floating,
      ),
    );
    if (widget.store.customerProfile != null) {
      Navigator.pushAndRemoveUntil(
        context,
        MaterialPageRoute(
          builder: (_) => CustomerHomeScreen(
            customer: widget.store.customerProfile!,
            store: widget.store,
          ),
        ),
        (route) => false,
      );
    } else if (Navigator.canPop(context)) {
      Navigator.pop(context);
    } else {
      setState(() {
        _verifiedShop = null;
        _tokenController.clear();
      });
      _initScanner();
    }
  }

  Widget _buildScannerPreview() {
    if (TokenStorageService.isTestEnvironment || !_isCameraInitialized) {
      return Container(
        height: 200,
        decoration: BoxDecoration(
          color: Colors.black87,
          borderRadius: BorderRadius.circular(20),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.15),
              blurRadius: 10,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        child: Stack(
          alignment: Alignment.center,
          children: [
            Container(
              width: 130,
              height: 130,
              decoration: BoxDecoration(
                border: Border.all(color: const Color(0xFF176B5B), width: 3),
                borderRadius: BorderRadius.circular(16),
              ),
            ),
            const Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(Icons.qr_code_scanner, color: Colors.white, size: 40),
                SizedBox(height: 8),
                Text(
                  'Scan Shop Registration QR',
                  style: TextStyle(color: Colors.white70, fontSize: 12),
                ),
              ],
            ),
          ],
        ),
      );
    }

    if (_isCameraPermissionDenied) {
      return Container(
        height: 200,
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: Colors.grey.shade900,
          borderRadius: BorderRadius.circular(20),
        ),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.no_photography_outlined, color: Colors.amber, size: 36),
            const SizedBox(height: 8),
            const Text(
              'Camera Permission Required',
              style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 14),
            ),
            const SizedBox(height: 4),
            const Text(
              'To scan QR codes, grant camera permission or use manual code entry below.',
              textAlign: TextAlign.center,
              style: TextStyle(color: Colors.white70, fontSize: 11),
            ),
            const SizedBox(height: 12),
            OutlinedButton.icon(
              style: OutlinedButton.styleFrom(
                foregroundColor: Colors.white,
                side: const BorderSide(color: Colors.white54),
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
              ),
              onPressed: () {
                setState(() => _isCameraPermissionDenied = false);
                _initScanner();
              },
              icon: const Icon(Icons.refresh, size: 16),
              label: const Text('Retry Camera', style: TextStyle(fontSize: 12)),
            ),
          ],
        ),
      );
    }

    return Container(
      height: 240,
      decoration: BoxDecoration(
        color: Colors.black,
        borderRadius: BorderRadius.circular(20),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.2),
            blurRadius: 12,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      clipBehavior: Clip.antiAlias,
      child: Stack(
        alignment: Alignment.center,
        children: [
          MobileScanner(
            controller: _scannerController,
            onDetect: _onBarcodeDetected,
            errorBuilder: (context, error) {
              if (error.errorCode == MobileScannerErrorCode.permissionDenied) {
                WidgetsBinding.instance.addPostFrameCallback((_) {
                  if (mounted && !_isCameraPermissionDenied) {
                    setState(() => _isCameraPermissionDenied = true);
                  }
                });
              }
              return Center(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const Icon(Icons.error_outline, color: Colors.orange, size: 36),
                      const SizedBox(height: 8),
                      Text(
                        error.errorCode == MobileScannerErrorCode.permissionDenied
                            ? 'Camera permission denied.'
                            : 'Camera unavailable: ${error.errorCode.message}',
                        textAlign: TextAlign.center,
                        style: const TextStyle(color: Colors.white, fontSize: 12),
                      ),
                    ],
                  ),
                ),
              );
            },
          ),
          // Viewfinder Target Frame
          Container(
            width: 160,
            height: 160,
            decoration: BoxDecoration(
              border: Border.all(color: const Color(0xFF176B5B), width: 3),
              borderRadius: BorderRadius.circular(20),
            ),
          ),
          // Camera Controls Overlay (Torch & Flip)
          Positioned(
            top: 10,
            right: 10,
            child: Row(
              children: [
                IconButton(
                  style: IconButton.styleFrom(backgroundColor: Colors.black45),
                  icon: Icon(
                    _isTorchOn ? Icons.flash_on : Icons.flash_off,
                    color: _isTorchOn ? Colors.amber : Colors.white,
                    size: 20,
                  ),
                  tooltip: 'Toggle Flash',
                  onPressed: _toggleTorch,
                ),
                const SizedBox(width: 6),
                IconButton(
                  style: IconButton.styleFrom(backgroundColor: Colors.black45),
                  icon: const Icon(Icons.cameraswitch_outlined, color: Colors.white, size: 20),
                  tooltip: 'Switch Camera',
                  onPressed: _switchCamera,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final isCustomerLoggedIn =
        widget.store.isAuthenticated && widget.store.activeSessionRole == 'customer';

    return Scaffold(
      backgroundColor: const Color(0xFFF6F8F7),
      appBar: AppBar(
        title: const Text(
          'Join Shop via QR',
          style: TextStyle(fontWeight: FontWeight.bold),
        ),
        backgroundColor: Colors.white,
        elevation: 0,
        foregroundColor: Colors.black87,
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(20),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 520),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                // 1. Live Camera QR Scanner Frame (hidden when shop is already verified)
                if (_verifiedShop == null) ...[
                  _buildScannerPreview(),
                  const SizedBox(height: 16),
                ],

                // 2. Manual Token / URL Entry Field
                Card(
                  elevation: 0,
                  color: Colors.white,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          'Registration Link or Token',
                          style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
                        ),
                        const SizedBox(height: 4),
                        const Text(
                          'Scan the shop standee QR or paste the link / token below:',
                          style: TextStyle(fontSize: 12, color: Colors.black54),
                        ),
                        const SizedBox(height: 12),
                        TextField(
                          controller: _tokenController,
                          decoration: InputDecoration(
                            hintText: 'e.g. http://192.168.1.5:8000/join/abc123xyz',
                            prefixIcon: const Icon(Icons.qr_code),
                            suffixIcon: IconButton(
                              icon: const Icon(Icons.arrow_forward_rounded, color: Color(0xFF176B5B)),
                              tooltip: 'Verify',
                              onPressed: () => _resolveToken(_tokenController.text),
                            ),
                            filled: true,
                            fillColor: const Color(0xFFF6F8F7),
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(12),
                              borderSide: BorderSide.none,
                            ),
                          ),
                          onSubmitted: _resolveToken,
                        ),
                        const SizedBox(height: 12),
                        SizedBox(
                          width: double.infinity,
                          child: FilledButton.icon(
                            style: FilledButton.styleFrom(
                              backgroundColor: const Color(0xFF176B5B),
                              padding: const EdgeInsets.symmetric(vertical: 12),
                              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                            ),
                            onPressed: _isResolving ? null : () => _resolveToken(_tokenController.text),
                            icon: _isResolving
                                ? const SizedBox(
                                    width: 16,
                                    height: 16,
                                    child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                                  )
                                : const Icon(Icons.verified_outlined, size: 18),
                            label: const Text('Verify Shop Code'),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),

                // 3. Error Banner
                if (_lookupError != null) ...[
                  const SizedBox(height: 16),
                  Container(
                    padding: const EdgeInsets.all(14),
                    decoration: BoxDecoration(
                      color: Colors.red.shade50,
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: Colors.red.shade200),
                    ),
                    child: Row(
                      children: [
                        Icon(Icons.error_outline, color: Colors.red.shade700, size: 20),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Text(
                            _lookupError!,
                            style: TextStyle(color: Colors.red.shade800, fontSize: 13),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],

                // 4. Verified Shop Presentation & Confirmation Card
                if (_verifiedShop != null) ...[
                  const SizedBox(height: 20),
                  Container(
                    padding: const EdgeInsets.all(20),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(20),
                      border: Border.all(color: const Color(0xFF176B5B), width: 1.5),
                      boxShadow: [
                        BoxShadow(
                          color: const Color(0xFF176B5B).withValues(alpha: 0.08),
                          blurRadius: 16,
                          offset: const Offset(0, 6),
                        ),
                      ],
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Container(
                              padding: const EdgeInsets.all(8),
                              decoration: const BoxDecoration(
                                color: Color(0xFFE2F1ED),
                                shape: BoxShape.circle,
                              ),
                              child: const Icon(Icons.verified, color: Color(0xFF176B5B), size: 24),
                            ),
                            const SizedBox(width: 12),
                            const Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    'VERIFIED QBOX MERCHANT',
                                    style: TextStyle(
                                      fontSize: 11,
                                      fontWeight: FontWeight.w800,
                                      letterSpacing: 0.8,
                                      color: Color(0xFF176B5B),
                                    ),
                                  ),
                                  Text(
                                    'Official Store Profile',
                                    style: TextStyle(fontSize: 12, color: Colors.black54),
                                  ),
                                ],
                              ),
                            ),
                          ],
                        ),
                        const Divider(height: 24),
                        Text(
                          _verifiedShop!.shopName,
                          style: const TextStyle(
                            fontSize: 22,
                            fontWeight: FontWeight.w800,
                            color: Colors.black87,
                          ),
                        ),
                        if (_verifiedShop!.shopAddress.isNotEmpty) ...[
                          const SizedBox(height: 6),
                          Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const Icon(Icons.location_on_outlined, size: 16, color: Colors.black45),
                              const SizedBox(width: 4),
                              Expanded(
                                child: Text(
                                  _verifiedShop!.shopAddress,
                                  style: const TextStyle(fontSize: 13, color: Colors.black54),
                                ),
                              ),
                            ],
                          ),
                        ],
                        const SizedBox(height: 16),

                        // Zero Balance & Credit Ledger Info
                        Container(
                          padding: const EdgeInsets.all(12),
                          decoration: BoxDecoration(
                            color: const Color(0xFFF6F8F7),
                            borderRadius: BorderRadius.circular(12),
                            border: Border.all(color: const Color(0xFFE2F1ED)),
                          ),
                          child: const Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                children: [
                                  Icon(Icons.shield_outlined, size: 18, color: Color(0xFF176B5B)),
                                  SizedBox(width: 8),
                                  Text(
                                    'Zero Initial Balance Guarantee',
                                    style: TextStyle(
                                      fontSize: 12,
                                      fontWeight: FontWeight.bold,
                                      color: Color(0xFF0F4B3F),
                                    ),
                                  ),
                                ],
                              ),
                              SizedBox(height: 4),
                              Text(
                                'Initial Udhaar balance is ₹0.00. No financial transactions, debit, credit or payments are made upon joining.',
                                style: TextStyle(fontSize: 11, color: Colors.black87, height: 1.3),
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(height: 20),

                        // Action Controls: If Logged In -> Confirmation Card; If Not Logged In -> Auth Options
                        if (isCustomerLoggedIn) ...[
                          // Explicit Confirmation Question
                          Container(
                            padding: const EdgeInsets.all(14),
                            decoration: BoxDecoration(
                              color: const Color(0xFFE2F1ED),
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: Text(
                              'Do you want to connect your Qbox account with ${_verifiedShop!.shopName}?',
                              style: const TextStyle(
                                fontSize: 14,
                                fontWeight: FontWeight.bold,
                                color: Color(0xFF0F4B3F),
                              ),
                              textAlign: TextAlign.center,
                            ),
                          ),
                          const SizedBox(height: 16),
                          Row(
                            children: [
                              Expanded(
                                child: OutlinedButton(
                                  style: OutlinedButton.styleFrom(
                                    foregroundColor: Colors.black87,
                                    side: BorderSide(color: Colors.grey.shade400),
                                    padding: const EdgeInsets.symmetric(vertical: 14),
                                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                                  ),
                                  onPressed: _isJoining ? null : _onCancelJoin,
                                  child: const Text('Cancel', style: TextStyle(fontWeight: FontWeight.w600)),
                                ),
                              ),
                              const SizedBox(width: 12),
                              Expanded(
                                flex: 2,
                                child: FilledButton.icon(
                                  style: FilledButton.styleFrom(
                                    backgroundColor: const Color(0xFF176B5B),
                                    foregroundColor: Colors.white,
                                    padding: const EdgeInsets.symmetric(vertical: 14),
                                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                                  ),
                                  onPressed: _isJoining ? null : _confirmJoinShop,
                                  icon: _isJoining
                                      ? const SizedBox(
                                          width: 18,
                                          height: 18,
                                          child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                                        )
                                      : const Icon(Icons.person_add_alt_1_rounded),
                                  label: Text(
                                    _isJoining ? 'Connecting...' : 'Join Shop',
                                    style: const TextStyle(fontSize: 15, fontWeight: FontWeight.bold),
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ] else ...[
                          Container(
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: Colors.amber.shade50,
                              borderRadius: BorderRadius.circular(10),
                              border: Border.all(color: Colors.amber.shade200),
                            ),
                            child: Row(
                              children: [
                                const Icon(Icons.lock_outline, size: 18, color: Colors.amber),
                                const SizedBox(width: 8),
                                Expanded(
                                  child: Text(
                                    'To connect with ${_verifiedShop!.shopName}, sign in or create an account. You will not need to scan again!',
                                    style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
                                  ),
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(height: 14),
                          Row(
                            children: [
                              Expanded(
                                child: OutlinedButton(
                                  style: OutlinedButton.styleFrom(
                                    foregroundColor: const Color(0xFF176B5B),
                                    side: const BorderSide(color: Color(0xFF176B5B)),
                                    padding: const EdgeInsets.symmetric(vertical: 14),
                                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                                  ),
                                  onPressed: () {
                                    Navigator.push(
                                      context,
                                      MaterialPageRoute(
                                        builder: (_) => CustomerLoginScreen(store: widget.store),
                                      ),
                                    );
                                  },
                                  child: const Text('Log In'),
                                ),
                              ),
                              const SizedBox(width: 10),
                              Expanded(
                                child: FilledButton(
                                  style: FilledButton.styleFrom(
                                    backgroundColor: const Color(0xFF176B5B),
                                    padding: const EdgeInsets.symmetric(vertical: 14),
                                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                                  ),
                                  onPressed: () {
                                    Navigator.push(
                                      context,
                                      MaterialPageRoute(
                                        builder: (_) => CustomerSignUpScreen(store: widget.store),
                                      ),
                                    );
                                  },
                                  child: const Text('Sign Up'),
                                ),
                              ),
                            ],
                          ),
                        ],
                      ],
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}
