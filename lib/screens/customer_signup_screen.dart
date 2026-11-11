import 'package:flutter/material.dart';
import '../main.dart';
import '../models/profiles.dart';
import '../services/api_service.dart';
import '../utils/validators.dart';
import 'customer_home_screen.dart';
import 'customer_login_screen.dart';
import 'scan_shop_qr_screen.dart';

/// Registration screen for customers connected to real PostgreSQL backend.
/// Contains strictly only 3 fields: Full name, Phone number, Address.
class CustomerSignUpScreen extends StatefulWidget {
  const CustomerSignUpScreen({
    super.key,
    required this.store,
    this.apiService,
  });

  final QboxStore store;
  final ApiService? apiService;

  @override
  State<CustomerSignUpScreen> createState() => _CustomerSignUpScreenState();
}

class _CustomerSignUpScreenState extends State<CustomerSignUpScreen> {
  final _formKey = GlobalKey<FormState>();

  final _fullNameController = TextEditingController();
  final _phoneController = TextEditingController();
  final _addressController = TextEditingController();
  final _passwordController = TextEditingController();
  bool _isLoading = false;
  String? _errorMessage;

  late final ApiService _apiService;

  @override
  void initState() {
    super.initState();
    _apiService = widget.apiService ?? ApiService();
  }

  @override
  void dispose() {
    _fullNameController.dispose();
    _phoneController.dispose();
    _addressController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_isLoading) return;
    if (!_formKey.currentState!.validate()) {
      return;
    }

    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    final normalizedPhone = Validators.normalizePhone(_phoneController.text);
    final password = _passwordController.text.trim().isEmpty ? 'Password@123' : _passwordController.text.trim();

    final result = await _apiService.registerCustomer(
      fullName: _fullNameController.text.trim(),
      phone: normalizedPhone,
      password: password,
      address: _addressController.text.trim(),
    );

    if (!mounted) return;

    if (result.isSuccess && result.data != null) {
      final customer = result.data!;
      widget.store.setCustomer(
        customer,
        token: customer.accessToken,
        refresh: customer.refreshToken,
      );

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          backgroundColor: const Color(0xFF176B5B),
          content: Text('Customer "${customer.fullName}" registered successfully!'),
          behavior: SnackBarBehavior.floating,
        ),
      );

      if (widget.store.pendingShopToken != null && widget.store.pendingShopToken!.isNotEmpty) {
        Navigator.pushAndRemoveUntil(
          context,
          MaterialPageRoute(
            builder: (_) => ScanShopQrScreen(
              store: widget.store,
              initialToken: widget.store.pendingShopToken,
            ),
          ),
          (route) => false,
        );
      } else {
        Navigator.pushAndRemoveUntil(
          context,
          MaterialPageRoute(
            builder: (_) => CustomerHomeScreen(
              customer: customer,
              store: widget.store,
            ),
          ),
          (route) => false,
        );
      }
    } else {
      final error = result.errorMessage ?? 'Customer registration failed.';
      setState(() {
        _errorMessage = error;
        _isLoading = false;
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
          'Customer Registration',
          style: TextStyle(fontWeight: FontWeight.bold),
        ),
        backgroundColor: Colors.white,
        elevation: 0,
        foregroundColor: Colors.black87,
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 20),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 520),
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
                          Icons.person_add_alt_1_rounded,
                          color: Color(0xFF176B5B),
                          size: 32,
                        ),
                        SizedBox(width: 12),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                'Create Customer Account',
                                style: TextStyle(
                                  fontWeight: FontWeight.bold,
                                  fontSize: 15,
                                  color: Color(0xFF176B5B),
                                ),
                              ),
                              SizedBox(height: 2),
                              Text(
                                'Sign up to track your purchases, verify store credits, and access digital receipts.',
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
                  const SizedBox(height: 20),

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

                  // Field 1: Full Name (Mandatory)
                  TextFormField(
                    controller: _fullNameController,
                    textCapitalization: TextCapitalization.words,
                    decoration: InputDecoration(
                      labelText: 'Full Name *',
                      hintText: 'e.g. Sravani Rao',
                      prefixIcon: const Icon(Icons.person_outline),
                      filled: true,
                      fillColor: Colors.white,
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                    ),
                    validator: (v) => Validators.validateRequired(v, 'Full name', minLength: 2),
                  ),
                  const SizedBox(height: 16),

                  // Field 2: Phone Number (Mandatory)
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
                  const SizedBox(height: 16),

                  // Field 3: Address (Mandatory)
                  TextFormField(
                    controller: _addressController,
                    maxLines: 2,
                    textCapitalization: TextCapitalization.sentences,
                    decoration: InputDecoration(
                      labelText: 'Home / Delivery Address *',
                      hintText: 'e.g. Flat 302, Sai Residency, Indiranagar, Bengaluru',
                      prefixIcon: const Icon(Icons.home_outlined),
                      filled: true,
                      fillColor: Colors.white,
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                    ),
                    validator: (v) => Validators.validateRequired(v, 'Address', minLength: 5),
                  ),
                  const SizedBox(height: 24),

                  // Submit Button
                  FilledButton.icon(
                    onPressed: _isLoading ? null : _submit,
                    icon: _isLoading
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                          )
                        : const Icon(Icons.check_circle_outline),
                    label: Text(
                      _isLoading ? 'Registering...' : 'Register as Customer',
                      style: const TextStyle(fontSize: 15, fontWeight: FontWeight.bold),
                    ),
                    style: FilledButton.styleFrom(
                      backgroundColor: const Color(0xFF176B5B),
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 16),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(14),
                      ),
                    ),
                  ),
                  const SizedBox(height: 20),

                  // Already have account? Log In
                  Wrap(
                    alignment: WrapAlignment.center,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: [
                      const Text(
                        "Already have a customer account? ",
                        style: TextStyle(fontSize: 13, color: Colors.black54),
                      ),
                      TextButton(
                        onPressed: () {
                          Navigator.pushReplacement(
                            context,
                            MaterialPageRoute(
                              builder: (_) => CustomerLoginScreen(store: widget.store),
                            ),
                          );
                        },
                        child: const Text(
                          'Log In',
                          style: TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.bold,
                            color: Color(0xFF176B5B),
                          ),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
