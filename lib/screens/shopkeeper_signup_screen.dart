import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';
import '../main.dart';
import '../models/profiles.dart';
import '../services/api_service.dart';
import '../utils/validators.dart';
import '../widgets/qr_preview_card.dart';

/// Registration screen for shopkeepers connected to real PostgreSQL backend.
class ShopkeeperSignUpScreen extends StatefulWidget {
  const ShopkeeperSignUpScreen({
    super.key,
    required this.store,
    this.apiService,
    this.imagePicker,
    this.paymentQrBytes,
    this.paymentQrFileName,
  });

  final QboxStore store;
  final ApiService? apiService;
  final ImagePicker? imagePicker;
  final Uint8List? paymentQrBytes;
  final String? paymentQrFileName;

  @override
  State<ShopkeeperSignUpScreen> createState() => _ShopkeeperSignUpScreenState();
}

class _ShopkeeperSignUpScreenState extends State<ShopkeeperSignUpScreen> {
  final _formKey = GlobalKey<FormState>();

  final _fullNameController = TextEditingController();
  final _shopNameController = TextEditingController();
  final _shopAddressController = TextEditingController();
  final _phoneController = TextEditingController();
  final _passwordController = TextEditingController();
  final _emailController = TextEditingController();
  final _upiIdController = TextEditingController();

  bool _obscurePassword = true;
  bool _isLoading = false;
  String? _errorMessage;
  String? _qrValidationError;

  XFile? _selectedQrFile;
  Uint8List? _selectedQrBytes;
  String? _selectedQrFileName;
  int? _selectedQrFileSize;
  String? _selectedQrName;

  late final ApiService _apiService;

  @override
  void initState() {
    super.initState();
    _apiService = widget.apiService ?? ApiService();
    if (widget.paymentQrBytes != null) {
      _selectedQrBytes = widget.paymentQrBytes;
      _selectedQrFileName = widget.paymentQrFileName ?? 'bhim_store_standee_qr.png';
      _selectedQrFileSize = widget.paymentQrBytes!.length;
      _selectedQrName = widget.paymentQrFileName ?? 'bhim_store_standee_qr.png';
    }
  }

  @override
  void dispose() {
    _fullNameController.dispose();
    _shopNameController.dispose();
    _shopAddressController.dispose();
    _phoneController.dispose();
    _passwordController.dispose();
    _emailController.dispose();
    _upiIdController.dispose();
    super.dispose();
  }

  Future<void> _pickPaymentQr() async {
    try {
      final picker = widget.imagePicker ?? ImagePicker();
      final picked = await picker.pickImage(source: ImageSource.gallery);

      if (picked == null) {
        // User cancelled picker
        return;
      }
      final file = picked;

      // Defensively resolve file name from XFile.name or XFile.path without assigning fake defaults
      String resolvedName = file.name.trim();
      if (resolvedName.isEmpty && file.path.isNotEmpty) {
        resolvedName = file.path.split(RegExp(r'[/\\]')).last.trim();
      }

      if (resolvedName.isEmpty) {
        setState(() {
          _qrValidationError = 'Unable to identify image filename. Please select a valid PNG or JPEG image.';
        });
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              backgroundColor: Colors.red.shade700,
              content: Text(_qrValidationError!),
              behavior: SnackBarBehavior.floating,
            ),
          );
        }
        return;
      }

      final lowerName = resolvedName.toLowerCase();
      final hasAllowedExt = lowerName.endsWith('.png') ||
          lowerName.endsWith('.jpg') ||
          lowerName.endsWith('.jpeg');

      if (!hasAllowedExt) {
        setState(() {
          _qrValidationError = 'Invalid image format. Only PNG, JPG, and JPEG images are allowed.';
        });
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              backgroundColor: Colors.red.shade700,
              content: Text(_qrValidationError!),
              behavior: SnackBarBehavior.floating,
            ),
          );
        }
        return;
      }

      final bytes = await file.readAsBytes();
      if (bytes.length > 5 * 1024 * 1024) {
        setState(() {
          _qrValidationError = 'File size exceeds 5 MB limit. Please select a smaller QR code image.';
        });
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              backgroundColor: Colors.red.shade700,
              content: Text(_qrValidationError!),
              behavior: SnackBarBehavior.floating,
            ),
          );
        }
        return;
      }

      // Validate actual image content headers (PNG: 0x89 0x50 0x4E 0x47 0x0D 0x0A 0x1A 0x0A; JPEG: 0xFF 0xD8 0xFF)
      final isPng = bytes.length >= 8 &&
          bytes[0] == 0x89 &&
          bytes[1] == 0x50 &&
          bytes[2] == 0x4E &&
          bytes[3] == 0x47 &&
          bytes[4] == 0x0D &&
          bytes[5] == 0x0A &&
          bytes[6] == 0x1A &&
          bytes[7] == 0x0A;
      final isJpg = bytes.length >= 3 &&
          bytes[0] == 0xFF &&
          bytes[1] == 0xD8 &&
          bytes[2] == 0xFF;

      if (!isPng && !isJpg) {
        setState(() {
          _qrValidationError = 'Invalid image content. Only valid PNG, JPG, and JPEG images are allowed.';
        });
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              backgroundColor: Colors.red.shade700,
              content: Text(_qrValidationError!),
              behavior: SnackBarBehavior.floating,
            ),
          );
        }
        return;
      }

      setState(() {
        _selectedQrFile = file;
        _selectedQrBytes = bytes;
        _selectedQrFileName = resolvedName;
        _selectedQrFileSize = bytes.length;
        _selectedQrName = resolvedName;
        _qrValidationError = null;
      });
    } catch (e) {
      setState(() {
        _qrValidationError = 'Failed to select image: $e';
      });
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            backgroundColor: Colors.red.shade700,
            content: Text(_qrValidationError!),
            behavior: SnackBarBehavior.floating,
          ),
        );
      }
    }
  }

  void _removePaymentQr() {
    setState(() {
      _selectedQrFile = null;
      _selectedQrBytes = null;
      _selectedQrFileName = null;
      _selectedQrFileSize = null;
      _selectedQrName = null;
      _qrValidationError = null;
    });
  }
  Future<void> _submit() async {
    if (_isLoading) return;

    if (!_formKey.currentState!.validate()) {
      return;
    }

    if (_selectedQrBytes == null && _selectedQrFile == null && _selectedQrName == null) {
      setState(() {
        _qrValidationError = 'Payment QR image is mandatory. Please upload your store UPI QR from gallery.';
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          backgroundColor: Colors.red.shade700,
          content: const Text('Payment QR image is mandatory. Please upload your store UPI QR from gallery.'),
          behavior: SnackBarBehavior.floating,
        ),
      );
      return;
    }

    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    final normalizedPhone = Validators.normalizePhone(_phoneController.text);
    final password = _passwordController.text.trim();

    final result = await _apiService.registerShopkeeper(
      fullName: _fullNameController.text.trim(),
      shopName: _shopNameController.text.trim(),
      shopAddress: _shopAddressController.text.trim(),
      phone: normalizedPhone,
      password: password,
      email: _emailController.text.trim().isEmpty ? null : _emailController.text.trim(),
      upiId: _upiIdController.text.trim().isEmpty ? null : _upiIdController.text.trim(),
      qrImageUrl: _selectedQrName,
      paymentQrFilePath: _selectedQrFile?.path,
      paymentQrBytes: _selectedQrBytes,
      paymentQrFileName: _selectedQrFileName ?? _selectedQrName,
    );

    if (!mounted) return;

    if (result.isSuccess && result.data != null) {
      final profile = result.data!;
      widget.store.setShopkeeper(
        profile,
        token: profile.accessToken,
        refresh: profile.refreshToken,
      );

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          backgroundColor: const Color(0xFF176B5B),
          content: Text('Shop "${profile.shopName}" registered successfully!'),
          behavior: SnackBarBehavior.floating,
        ),
      );

      // Navigate to shopkeeper dashboard, replacing registration
      Navigator.pushAndRemoveUntil(
        context,
        MaterialPageRoute(builder: (_) => HomeScreen(store: widget.store, apiService: _apiService)),
        (route) => false,
      );
    } else {
      final error = result.errorMessage ?? 'Registration failed. Please try again.';

      setState(() {
        _isLoading = false;
        _errorMessage = error;
      });

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          backgroundColor: Colors.red.shade700,
          content: Text(_errorMessage!),
          behavior: SnackBarBehavior.floating,
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF6F8F7),
      appBar: AppBar(
        title: const Text(
          'Shopkeeper Registration',
          style: TextStyle(fontWeight: FontWeight.bold),
        ),
        backgroundColor: Colors.white,
        elevation: 0,
        foregroundColor: Colors.black87,
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 18),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 540),
            child: Form(
              key: _formKey,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  // Header Banner
                  Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: const Color(0xFFE2F1ED),
                      borderRadius: BorderRadius.circular(16),
                      border: Border.all(color: const Color(0xFFBCE3D7)),
                    ),
                    child: const Row(
                      children: [
                        Icon(
                          Icons.store_rounded,
                          color: Color(0xFF176B5B),
                          size: 32,
                        ),
                        SizedBox(width: 12),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                'Register Your Business',
                                style: TextStyle(
                                  fontWeight: FontWeight.bold,
                                  fontSize: 15,
                                  color: Color(0xFF176B5B),
                                ),
                              ),
                              SizedBox(height: 2),
                              Text(
                                'Create your shopkeeper account. All business data is securely stored in PostgreSQL.',
                                style: TextStyle(
                                  fontSize: 11,
                                  color: Colors.black87,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 16),

                  // Backend Error Alert Banner with Retry Button
                  if (_errorMessage != null) ...[
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: Colors.red.shade50,
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: Colors.red.shade300),
                      ),
                      child: Row(
                        children: [
                          Icon(Icons.error_outline, color: Colors.red.shade700, size: 20),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Text(
                              _errorMessage!,
                              style: TextStyle(
                                color: Colors.red.shade900,
                                fontSize: 13,
                                fontWeight: FontWeight.w500,
                              ),
                            ),
                          ),
                          TextButton(
                            onPressed: _isLoading ? null : _submit,
                            style: TextButton.styleFrom(
                              foregroundColor: Colors.red.shade900,
                              padding: const EdgeInsets.symmetric(horizontal: 8),
                              visualDensity: VisualDensity.compact,
                            ),
                            child: const Text(
                              'Retry',
                              style: TextStyle(fontWeight: FontWeight.bold),
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 14),
                  ],

                  // 1. Full Name
                  TextFormField(
                    controller: _fullNameController,
                    textCapitalization: TextCapitalization.words,
                    decoration: InputDecoration(
                      labelText: 'Full Name *',
                      hintText: 'e.g. Ramesh Chandra',
                      prefixIcon: const Icon(Icons.person_outline),
                      filled: true,
                      fillColor: Colors.white,
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                    ),
                    validator: (v) => Validators.validateRequired(v, 'Full name', minLength: 2),
                  ),
                  const SizedBox(height: 14),

                  // 2. Shop Name
                  TextFormField(
                    controller: _shopNameController,
                    textCapitalization: TextCapitalization.words,
                    decoration: InputDecoration(
                      labelText: 'Shop / Business Name *',
                      hintText: 'e.g. Chandra Kirana & Provisions',
                      prefixIcon: const Icon(Icons.storefront_outlined),
                      filled: true,
                      fillColor: Colors.white,
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                    ),
                    validator: (v) => Validators.validateRequired(v, 'Shop name', minLength: 2),
                  ),
                  const SizedBox(height: 14),

                  // 3. Shop Address
                  TextFormField(
                    controller: _shopAddressController,
                    maxLines: 2,
                    textCapitalization: TextCapitalization.sentences,
                    decoration: InputDecoration(
                      labelText: 'Shop Address *',
                      hintText: 'e.g. Shop #12, Market Main Road, Bengaluru',
                      prefixIcon: const Icon(Icons.location_on_outlined),
                      filled: true,
                      fillColor: Colors.white,
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                    ),
                    validator: (v) => Validators.validateRequired(v, 'Shop address', minLength: 5),
                  ),
                  const SizedBox(height: 14),

                  // 4. Phone Number
                  TextFormField(
                    controller: _phoneController,
                    keyboardType: TextInputType.phone,
                    decoration: InputDecoration(
                      labelText: 'Phone Number *',
                      hintText: '10-digit mobile number',
                      prefixText: '+91 ',
                      prefixIcon: const Icon(Icons.phone_outlined),
                      filled: true,
                      fillColor: Colors.white,
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                    ),
                    validator: Validators.validatePhone,
                  ),
                  const SizedBox(height: 14),

                  // 5. Password Field
                  TextFormField(
                    controller: _passwordController,
                    obscureText: _obscurePassword,
                    decoration: InputDecoration(
                      labelText: 'Account Password *',
                      hintText: 'Minimum 8 characters',
                      prefixIcon: const Icon(Icons.lock_outline),
                      suffixIcon: IconButton(
                        icon: Icon(
                          _obscurePassword ? Icons.visibility_outlined : Icons.visibility_off_outlined,
                          color: Colors.black54,
                        ),
                        onPressed: () => setState(() => _obscurePassword = !_obscurePassword),
                      ),
                      filled: true,
                      fillColor: Colors.white,
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                      helperText: 'Secured via Argon2id hashing on backend.',
                    ),
                    validator: Validators.validatePassword,
                  ),
                  const SizedBox(height: 14),

                  // 6. Optional Email Field
                  TextFormField(
                    controller: _emailController,
                    keyboardType: TextInputType.emailAddress,
                    decoration: InputDecoration(
                      labelText: 'Email Address (Optional)',
                      hintText: 'e.g. ramesh@example.com',
                      prefixIcon: const Icon(Icons.email_outlined),
                      filled: true,
                      fillColor: Colors.white,
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                    ),
                  ),
                  const SizedBox(height: 20),

                  // 7. Upload Payment QR Code (Mandatory)
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text(
                        'Upload Payment QR Code *',
                        style: TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.bold,
                          color: Colors.black87,
                        ),
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                        decoration: BoxDecoration(
                          color: const Color(0xFFE2F1ED),
                          borderRadius: BorderRadius.circular(6),
                          border: Border.all(color: const Color(0xFF176B5B), width: 0.5),
                        ),
                        child: const Text(
                          'MANDATORY',
                          style: TextStyle(
                            fontSize: 10,
                            fontWeight: FontWeight.bold,
                            color: Color(0xFF176B5B),
                            letterSpacing: 0.5,
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 4),
                  const Text(
                    'Upload your store UPI QR standee from gallery (PhonePe, GPay, Paytm, BHIM, Bank QR). PNG/JPG up to 5 MB.',
                    style: TextStyle(fontSize: 12, color: Colors.black54),
                  ),
                  const SizedBox(height: 10),

                  if (_selectedQrBytes == null && _selectedQrName == null) ...[
                    // Empty State: Prompt to upload from gallery
                    Container(
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(14),
                        border: Border.all(
                          color: _qrValidationError != null ? Colors.red.shade400 : const Color(0xFFD0D7D4),
                          width: _qrValidationError != null ? 1.5 : 1,
                        ),
                      ),
                      padding: const EdgeInsets.all(20),
                      child: Column(
                        children: [
                          const Icon(
                            Icons.qr_code_scanner,
                            size: 40,
                            color: Color(0xFF176B5B),
                          ),
                          const SizedBox(height: 8),
                          const Text(
                            'No Payment QR Uploaded',
                            style: TextStyle(
                              fontWeight: FontWeight.bold,
                              fontSize: 14,
                            ),
                          ),
                          const SizedBox(height: 4),
                          const Text(
                            'Select your static UPI payment QR image from your phone gallery.',
                            style: TextStyle(fontSize: 12, color: Colors.black54),
                            textAlign: TextAlign.center,
                          ),
                          const SizedBox(height: 14),
                          FilledButton.tonalIcon(
                            onPressed: _pickPaymentQr,
                            icon: const Icon(Icons.photo_library_outlined, size: 18),
                            label: const Text('Upload from Gallery'),
                            style: FilledButton.styleFrom(
                              backgroundColor: const Color(0xFFE2F1ED),
                              foregroundColor: const Color(0xFF176B5B),
                              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(10),
                              ),
                            ),
                          ),
                          if (_qrValidationError != null) ...[
                            const SizedBox(height: 12),
                            Row(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                Icon(Icons.error_outline, size: 16, color: Colors.red.shade700),
                                const SizedBox(width: 6),
                                Flexible(
                                  child: Text(
                                    _qrValidationError!,
                                    style: TextStyle(
                                      color: Colors.red.shade700,
                                      fontSize: 12,
                                      fontWeight: FontWeight.w500,
                                    ),
                                    textAlign: TextAlign.center,
                                  ),
                                ),
                              ],
                            ),
                          ],
                        ],
                      ),
                    ),
                  ] else ...[
                    // Preview State: Display QR Preview Card with image preview, size, replace and remove actions
                    QrPreviewCard(
                      qrName: _selectedQrFileName ?? _selectedQrName ?? 'Store Payment QR',
                      shopName: _shopNameController.text.trim(),
                      upiId: _upiIdController.text.trim(),
                      imageBytes: _selectedQrBytes,
                      fileSizeBytes: _selectedQrFileSize,
                      replaceLabel: 'Replace QR',
                      onChange: _pickPaymentQr,
                      onRemove: _removePaymentQr,
                    ),
                  ],
                  const SizedBox(height: 14),

                  // 8. UPI ID (Optional)
                  TextFormField(
                    controller: _upiIdController,
                    keyboardType: TextInputType.emailAddress,
                    onChanged: (_) {
                      if (_selectedQrName != null) setState(() {});
                    },
                    decoration: InputDecoration(
                      labelText: 'UPI ID (Optional)',
                      hintText: 'e.g. shopname@upi or 9876543210@paytm',
                      prefixIcon: const Icon(Icons.account_balance_outlined),
                      filled: true,
                      fillColor: Colors.white,
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                      helperText: 'Customers can use this UPI address for direct payments.',
                    ),
                    validator: Validators.validateUpi,
                  ),
                  const SizedBox(height: 24),

                  // Submit Button
                  FilledButton(
                    onPressed: _isLoading ? null : _submit,
                    style: FilledButton.styleFrom(
                      backgroundColor: const Color(0xFF176B5B),
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 16),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(14),
                      ),
                    ),
                    child: _isLoading
                        ? const SizedBox(
                            height: 20,
                            width: 20,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: Colors.white,
                            ),
                          )
                        : const Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Icon(Icons.check_circle_outline),
                              SizedBox(width: 8),
                              Text(
                                'Register & Open Shop',
                                style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold),
                              ),
                            ],
                          ),
                  ),
                  const SizedBox(height: 16),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
