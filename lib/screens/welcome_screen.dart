import 'package:flutter/material.dart';
import '../config/app_config.dart';
import '../main.dart';
import 'customer_login_screen.dart';
import 'customer_signup_screen.dart';
import 'scan_shop_qr_screen.dart';
import 'shopkeeper_login_screen.dart';
import 'shopkeeper_signup_screen.dart';

/// The first screen displayed whenever Qbox opens.
/// Presents role selection between Shopkeeper and Customer.
class WelcomeScreen extends StatefulWidget {
  const WelcomeScreen({super.key, required this.store});

  final QboxStore store;

  @override
  State<WelcomeScreen> createState() => _WelcomeScreenState();
}

class _WelcomeScreenState extends State<WelcomeScreen> {
  void _showEnvironmentDialog() {
    final customController = TextEditingController(text: AppConfig.baseUrl);
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Row(
          children: [
            Icon(Icons.wifi_tethering, color: Color(0xFF176B5B)),
            SizedBox(width: 8),
            Text('Target Backend'),
          ],
        ),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Select which backend instance this app connects to:',
                style: TextStyle(fontSize: 12, color: Colors.black54),
              ),
              const SizedBox(height: 12),
              ListTile(
                dense: true,
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.phone_android, color: Color(0xFF176B5B)),
                title: const Text('Android Emulator', style: TextStyle(fontWeight: FontWeight.w600)),
                subtitle: const Text('http://10.0.2.2:8000'),
                trailing: AppConfig.activeEnvironment == AppEnvironment.emulator
                    ? const Icon(Icons.check_circle, color: Color(0xFF176B5B), size: 18)
                    : null,
                onTap: () {
                  AppConfig.setEnvironment(AppEnvironment.emulator);
                  Navigator.pop(ctx);
                  setState(() {});
                },
              ),
              ListTile(
                dense: true,
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.wifi, color: Color(0xFF176B5B)),
                title: const Text('Physical Android Phone', style: TextStyle(fontWeight: FontWeight.w600)),
                subtitle: Text('http://${AppConfig.devHostIp}:${AppConfig.devPort}'),
                trailing: AppConfig.activeEnvironment == AppEnvironment.physicalDevice
                    ? const Icon(Icons.check_circle, color: Color(0xFF176B5B), size: 18)
                    : null,
                onTap: () {
                  AppConfig.setEnvironment(AppEnvironment.physicalDevice);
                  Navigator.pop(ctx);
                  setState(() {});
                },
              ),
              ListTile(
                dense: true,
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.computer, color: Color(0xFF176B5B)),
                title: const Text('Localhost / Desktop', style: TextStyle(fontWeight: FontWeight.w600)),
                subtitle: const Text('http://127.0.0.1:8000'),
                trailing: AppConfig.activeEnvironment == AppEnvironment.localhost
                    ? const Icon(Icons.check_circle, color: Color(0xFF176B5B), size: 18)
                    : null,
                onTap: () {
                  AppConfig.setEnvironment(AppEnvironment.localhost);
                  Navigator.pop(ctx);
                  setState(() {});
                },
              ),
              const Divider(),
              const Text('Or Enter Custom Base URL:', style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold)),
              const SizedBox(height: 6),
              TextField(
                controller: customController,
                decoration: const InputDecoration(
                  hintText: 'http://192.168.1.5:8000',
                  isDense: true,
                  border: OutlineInputBorder(),
                ),
                style: const TextStyle(fontSize: 12),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Cancel'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: const Color(0xFF176B5B)),
            onPressed: () {
              final val = customController.text.trim();
              if (val.isNotEmpty) {
                AppConfig.setBaseUrl(val);
                Navigator.pop(ctx);
                setState(() {});
              }
            },
            child: const Text('Apply'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF6F8F7),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 520),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  // Brand Header
                  const SizedBox(height: 12),
                  Center(
                    child: Container(
                      width: 76,
                      height: 76,
                      decoration: BoxDecoration(
                        gradient: const LinearGradient(
                          colors: [Color(0xFF176B5B), Color(0xFF0F4B3F)],
                          begin: Alignment.topLeft,
                          end: Alignment.bottomRight,
                        ),
                        borderRadius: BorderRadius.circular(22),
                        boxShadow: [
                          BoxShadow(
                            color: const Color(0xFF176B5B).withValues(alpha: 0.28),
                            blurRadius: 16,
                            offset: const Offset(0, 8),
                          ),
                        ],
                      ),
                      child: const Center(
                        child: Text(
                          'Q',
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: 42,
                            fontWeight: FontWeight.w900,
                            letterSpacing: -1,
                          ),
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(height: 18),
                  const Center(
                    child: Text(
                      'Qbox',
                      style: TextStyle(
                        fontSize: 32,
                        fontWeight: FontWeight.w900,
                        color: Color(0xFF176B5B),
                        letterSpacing: -0.5,
                      ),
                    ),
                  ),
                  const SizedBox(height: 6),
                  const Center(
                    child: Text(
                      'Your Shop. Your Business. Simplified.',
                      style: TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.w600,
                        color: Colors.black87,
                      ),
                      textAlign: TextAlign.center,
                    ),
                  ),
                  const SizedBox(height: 6),
                  const Center(
                    child: Text(
                      'Smart Digital Khata, Udhaar Tracking & Instant Receipts',
                      style: TextStyle(
                        fontSize: 12,
                        color: Colors.black54,
                      ),
                      textAlign: TextAlign.center,
                    ),
                  ),
                  const SizedBox(height: 32),

                  // Section Title
                  Row(
                    children: [
                      Container(
                        width: 4,
                        height: 18,
                        decoration: BoxDecoration(
                          color: const Color(0xFF176B5B),
                          borderRadius: BorderRadius.circular(2),
                        ),
                      ),
                      const SizedBox(width: 8),
                      const Text(
                        'Select Your Role to Continue',
                        style: TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w700,
                          color: Colors.black87,
                          letterSpacing: 0.2,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),

                  // Role Option 1: Shopkeeper Card
                  _RoleCard(
                    icon: Icons.storefront_rounded,
                    roleTitle: "I'm a Shopkeeper",
                    roleDescription:
                        'Manage customer credit, record daily payments, track Udhaar balances & view ledger.',
                    badgeText: 'MERCHANT',
                    onSignUp: () {
                      Navigator.push(
                        context,
                        MaterialPageRoute(
                          builder: (_) => ShopkeeperSignUpScreen(store: widget.store),
                        ),
                      );
                    },
                    onLogin: () {
                      Navigator.push(
                        context,
                        MaterialPageRoute(
                          builder: (_) => ShopkeeperLoginScreen(store: widget.store),
                        ),
                      );
                    },
                  ),
                  const SizedBox(height: 20),

                  // Role Option 2: Customer Card
                  _RoleCard(
                    icon: Icons.person_rounded,
                    roleTitle: "I'm a Customer",
                    roleDescription:
                        'Check your store credit balance, view repayments, and access digital receipts.',
                    badgeText: 'BUYER',
                    onSignUp: () {
                      Navigator.push(
                        context,
                        MaterialPageRoute(
                          builder: (_) => CustomerSignUpScreen(store: widget.store),
                        ),
                      );
                    },
                    onLogin: () {
                      Navigator.push(
                        context,
                        MaterialPageRoute(
                          builder: (_) => CustomerLoginScreen(store: widget.store),
                        ),
                      );
                    },
                  ),
                  const SizedBox(height: 20),

                  // Option 3: Customer QR Onboarding Entry Point
                  Container(
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
                          padding: const EdgeInsets.all(10),
                          decoration: BoxDecoration(
                            color: const Color(0xFFE2F1ED),
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: const Icon(
                            Icons.qr_code_scanner,
                            color: Color(0xFF176B5B),
                            size: 24,
                          ),
                        ),
                        const SizedBox(width: 12),
                        const Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                'Have a Shop QR Code?',
                                style: TextStyle(
                                  fontSize: 14,
                                  fontWeight: FontWeight.bold,
                                  color: Color(0xFF176B5B),
                                ),
                              ),
                              SizedBox(height: 2),
                              Text(
                                'Scan store QR to join merchant khata & receive bills',
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
                              MaterialPageRoute(
                                builder: (_) => ScanShopQrScreen(store: widget.store),
                              ),
                            );
                          },
                          child: const Text('Scan QR', style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold)),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 24),

                  // Footer Info
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                    decoration: BoxDecoration(
                      color: const Color(0xFFE2F1ED),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: const Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(
                          Icons.verified_user_outlined,
                          size: 16,
                          color: Color(0xFF176B5B),
                        ),
                        SizedBox(width: 8),
                        Flexible(
                          child: Text(
                            'Local Demo Mode • Integer Paise Calculations',
                            style: TextStyle(
                              fontSize: 11,
                              fontWeight: FontWeight.w600,
                              color: Color(0xFF176B5B),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 12),

                  // Target Environment Chip / Selector
                  Center(
                    child: InkWell(
                      onTap: _showEnvironmentDialog,
                      borderRadius: BorderRadius.circular(10),
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
                        decoration: BoxDecoration(
                          color: Colors.white,
                          borderRadius: BorderRadius.circular(10),
                          border: Border.all(color: Colors.black12),
                          boxShadow: [
                            BoxShadow(
                              color: Colors.black.withValues(alpha: 0.03),
                              blurRadius: 4,
                              offset: const Offset(0, 2),
                            ),
                          ],
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            const Icon(Icons.wifi_tethering, size: 14, color: Color(0xFF176B5B)),
                            const SizedBox(width: 6),
                            Text(
                              'Target: ${AppConfig.environmentLabel}',
                              style: const TextStyle(fontSize: 11, color: Colors.black87, fontWeight: FontWeight.w500),
                            ),
                            const SizedBox(width: 4),
                            const Icon(Icons.arrow_drop_down, size: 16, color: Colors.black54),
                          ],
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _RoleCard extends StatelessWidget {
  const _RoleCard({
    required this.icon,
    required this.roleTitle,
    required this.roleDescription,
    required this.badgeText,
    required this.onSignUp,
    required this.onLogin,
  });

  final IconData icon;
  final String roleTitle;
  final String roleDescription;
  final String badgeText;
  final VoidCallback onSignUp;
  final VoidCallback onLogin;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: const Color(0xFFE0E5E3), width: 1.2),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.04),
            blurRadius: 12,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              Container(
                width: 48,
                height: 48,
                decoration: BoxDecoration(
                  color: const Color(0xFFE2F1ED),
                  borderRadius: BorderRadius.circular(14),
                ),
                child: Icon(icon, color: const Color(0xFF176B5B), size: 26),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Flexible(
                          child: Text(
                            roleTitle,
                            style: const TextStyle(
                              fontSize: 18,
                              fontWeight: FontWeight.w800,
                              color: Colors.black87,
                            ),
                          ),
                        ),
                        const SizedBox(width: 8),
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 6,
                            vertical: 2,
                          ),
                          decoration: BoxDecoration(
                            color: const Color(0xFF176B5B).withValues(alpha: 0.08),
                            borderRadius: BorderRadius.circular(6),
                          ),
                          child: Text(
                            badgeText,
                            style: const TextStyle(
                              fontSize: 9,
                              fontWeight: FontWeight.w800,
                              color: Color(0xFF176B5B),
                              letterSpacing: 0.5,
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 2),
                    Text(
                      roleDescription,
                      style: const TextStyle(
                        fontSize: 12,
                        color: Colors.black54,
                        height: 1.3,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          const Divider(height: 1, color: Color(0xFFF0F3F2)),
          const SizedBox(height: 14),

          // Two Options: Sign Up & Login
          Row(
            children: [
              Expanded(
                child: FilledButton(
                  onPressed: onSignUp,
                  style: FilledButton.styleFrom(
                    backgroundColor: const Color(0xFF176B5B),
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 12),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                  ),
                  child: const Text(
                    'Sign Up',
                    style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
                  ),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: OutlinedButton(
                  onPressed: onLogin,
                  style: OutlinedButton.styleFrom(
                    foregroundColor: const Color(0xFF176B5B),
                    side: const BorderSide(color: Color(0xFF176B5B), width: 1.2),
                    padding: const EdgeInsets.symmetric(vertical: 12),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                  ),
                  child: const Text(
                    'Login',
                    style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
