import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../main.dart';
import '../models/profiles.dart';
import '../services/api_service.dart';

/// Modal bottom sheet displaying a merchant's static UPI Payment QR for connected customers.
class CustomerPaymentQrSheet extends StatefulWidget {
  const CustomerPaymentQrSheet({
    super.key,
    required this.shop,
    required this.store,
    required this.customer,
    this.apiService,
  });

  final CustomerJoinedShop shop;
  final QboxStore store;
  final RegisteredCustomer customer;
  final ApiService? apiService;

  @override
  State<CustomerPaymentQrSheet> createState() => _CustomerPaymentQrSheetState();
}

class _CustomerPaymentQrSheetState extends State<CustomerPaymentQrSheet> {
  late final ApiService _apiService;
  bool _isLoading = true;
  String? _errorMessage;
  CustomerShopPaymentQr? _paymentQrData;
  Uint8List? _imageBytes;
  bool _isCopied = false;

  @override
  void initState() {
    super.initState();
    _apiService = widget.apiService ?? ApiService();
    _fetchPaymentQr();
  }

  Future<void> _fetchPaymentQr() async {
    final token = widget.store.accessToken ?? widget.customer.accessToken;
    if (token == null || token.isEmpty) {
      if (mounted) {
        setState(() {
          _isLoading = false;
          _errorMessage = 'Authentication required to view payment QR.';
        });
      }
      return;
    }

    final res = await _apiService.getCustomerShopPaymentQr(
      widget.shop.shopId,
      authToken: token,
    );

    if (!mounted) return;

    if (res.isSuccess && res.data != null) {
      final data = res.data!;
      setState(() {
        _paymentQrData = data;
        _isLoading = false;
      });

      if (data.hasPaymentQr && data.paymentQrUrl != null) {
        _downloadImage(data.paymentQrUrl!, token);
      }
    } else {
      setState(() {
        _errorMessage = res.errorMessage ?? 'Unable to load payment QR code.';
        _isLoading = false;
      });
    }
  }

  Future<void> _downloadImage(String imageUrl, String token) async {
    final imgRes = await _apiService.downloadPaymentQrImage(
      url: imageUrl,
      authToken: token,
    );
    if (!mounted) return;
    if (imgRes.isSuccess && imgRes.data != null) {
      setState(() {
        _imageBytes = imgRes.data;
      });
    }
  }

  void _copyUpiId(String upiId) {
    Clipboard.setData(ClipboardData(text: upiId));
    setState(() => _isCopied = true);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Copied "$upiId" to clipboard'),
        behavior: SnackBarBehavior.floating,
        duration: const Duration(seconds: 2),
      ),
    );
    Future.delayed(const Duration(seconds: 3), () {
      if (mounted) setState(() => _isCopied = false);
    });
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.only(
          left: 20,
          right: 20,
          top: 20,
          bottom: MediaQuery.of(context).viewInsets.bottom + 20,
        ),
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // Header Row
              Row(
                children: [
                  const Icon(Icons.qr_code_2_rounded, color: Color(0xFF176B5B), size: 28),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          widget.shop.shopName,
                          style: const TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.bold,
                          ),
                          overflow: TextOverflow.ellipsis,
                        ),
                        const Text(
                          'Store UPI Payment QR',
                          style: TextStyle(fontSize: 12, color: Colors.black54),
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Icons.close),
                    onPressed: () => Navigator.pop(context),
                  ),
                ],
              ),
              const Divider(height: 24),

              if (_isLoading)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 40),
                  child: Center(
                    child: CircularProgressIndicator(color: Color(0xFF176B5B)),
                  ),
                )
              else if (_errorMessage != null)
                Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: Colors.red.shade50,
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: Colors.red.shade200),
                  ),
                  child: Column(
                    children: [
                      Icon(Icons.error_outline, color: Colors.red.shade700, size: 32),
                      const SizedBox(height: 8),
                      Text(
                        _errorMessage!,
                        style: TextStyle(
                          color: Colors.red.shade900,
                          fontSize: 13,
                          fontWeight: FontWeight.w500,
                        ),
                        textAlign: TextAlign.center,
                      ),
                      const SizedBox(height: 12),
                      OutlinedButton(
                        onPressed: () {
                          setState(() {
                            _isLoading = true;
                            _errorMessage = null;
                          });
                          _fetchPaymentQr();
                        },
                        child: const Text('Try Again'),
                      ),
                    ],
                  ),
                )
              else if (_paymentQrData != null && !_paymentQrData!.hasPaymentQr)
                Container(
                  padding: const EdgeInsets.all(24),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(color: const Color(0xFFE0E5E3)),
                  ),
                  child: const Column(
                    children: [
                      Icon(Icons.qr_code_scanner, size: 48, color: Colors.grey),
                      SizedBox(height: 12),
                      Text(
                        'No Payment QR Uploaded',
                        style: TextStyle(fontWeight: FontWeight.bold, fontSize: 15),
                      ),
                      SizedBox(height: 6),
                      Text(
                        'This shopkeeper has not uploaded a static UPI payment QR code yet. Please check with the merchant directly.',
                        style: TextStyle(fontSize: 12, color: Colors.black54),
                        textAlign: TextAlign.center,
                      ),
                    ],
                  ),
                )
              else if (_paymentQrData != null) ...[
                // Active Payment QR Box
                Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(16),
                    border: Border.all(color: const Color(0xFF176B5B), width: 1.5),
                    boxShadow: [
                      BoxShadow(
                        color: Colors.black.withValues(alpha: 0.04),
                        blurRadius: 10,
                        offset: const Offset(0, 4),
                      ),
                    ],
                  ),
                  child: Column(
                    children: [
                      // QR Code Image
                      Container(
                        width: 220,
                        height: 220,
                        decoration: BoxDecoration(
                          color: Colors.white,
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(color: Colors.black12),
                        ),
                        alignment: Alignment.center,
                        child: _imageBytes != null
                            ? ClipRRect(
                                borderRadius: BorderRadius.circular(10),
                                child: Image.memory(
                                  _imageBytes!,
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
                                  Text(
                                    'Loading QR image...',
                                    style: TextStyle(fontSize: 11, color: Colors.black54),
                                  ),
                                ],
                              ),
                      ),
                      const SizedBox(height: 12),

                      // Provider Badge
                      if (_paymentQrData!.upiProvider != null && _paymentQrData!.upiProvider!.isNotEmpty)
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                          decoration: BoxDecoration(
                            color: const Color(0xFFE2F1ED),
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: Text(
                            '${_paymentQrData!.upiProvider} UPI',
                            style: const TextStyle(
                              fontSize: 11,
                              fontWeight: FontWeight.bold,
                              color: Color(0xFF176B5B),
                            ),
                          ),
                        ),

                      if (_paymentQrData!.upiId != null && _paymentQrData!.upiId!.isNotEmpty) ...[
                        const SizedBox(height: 10),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                          decoration: BoxDecoration(
                            color: const Color(0xFFF6F8F7),
                            borderRadius: BorderRadius.circular(10),
                            border: Border.all(color: const Color(0xFFE0E5E3)),
                          ),
                          child: Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              const Icon(Icons.account_balance, size: 16, color: Color(0xFF176B5B)),
                              const SizedBox(width: 8),
                              Flexible(
                                child: Text(
                                  _paymentQrData!.upiId!,
                                  style: const TextStyle(
                                    fontWeight: FontWeight.bold,
                                    fontSize: 13,
                                  ),
                                  overflow: TextOverflow.ellipsis,
                                ),
                              ),
                              const SizedBox(width: 8),
                              IconButton(
                                icon: Icon(
                                  _isCopied ? Icons.check : Icons.copy,
                                  size: 16,
                                  color: const Color(0xFF176B5B),
                                ),
                                onPressed: () => _copyUpiId(_paymentQrData!.upiId!),
                                tooltip: 'Copy UPI ID',
                                padding: EdgeInsets.zero,
                                constraints: const BoxConstraints(),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
                const SizedBox(height: 16),

                // Non-custodial Disclaimer Banner
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: const Color(0xFFFFF8E1),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: const Color(0xFFFFE082)),
                  ),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Icon(Icons.info_outline, color: Color(0xFFF57F17), size: 20),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text(
                              'Non-Custodial Direct UPI Payment',
                              style: TextStyle(
                                fontWeight: FontWeight.bold,
                                fontSize: 12,
                                color: Color(0xFFE65100),
                              ),
                            ),
                            const SizedBox(height: 3),
                            Text(
                              _paymentQrData!.disclaimer,
                              style: const TextStyle(
                                fontSize: 11,
                                color: Color(0xFF5D4037),
                                height: 1.3,
                              ),
                            ),
                            const SizedBox(height: 4),
                            const Text(
                              'Save your UPI transaction reference. Qbox does not auto-deduct funds or verify payments automatically.',
                              style: TextStyle(
                                fontSize: 10,
                                fontStyle: FontStyle.italic,
                                color: Color(0xFF8D6E63),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 16),

                // Done Button
                FilledButton(
                  onPressed: () => Navigator.pop(context),
                  style: FilledButton.styleFrom(
                    backgroundColor: const Color(0xFF176B5B),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                    padding: const EdgeInsets.symmetric(vertical: 14),
                  ),
                  child: const Text('Done', style: TextStyle(fontWeight: FontWeight.bold)),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

