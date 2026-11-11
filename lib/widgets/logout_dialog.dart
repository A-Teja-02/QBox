import 'package:flutter/material.dart';
import '../main.dart';
import '../screens/welcome_screen.dart';
import '../services/api_service.dart';

/// Displays the standard Qbox logout confirmation dialog and handles
/// session clearing and navigation stack reset.
///
/// Dialog specification:
/// - Message: "Are you sure you want to log out?"
/// - Actions: "Cancel" and "Logout"
///
/// On Cancel: Dismisses the dialog and remains on the current screen.
/// On Logout:
/// - Clears the current authenticated/demo session
/// - Invalidates refresh token session on the backend server
/// - Wipes tokens from hardware secure storage (flutter_secure_storage)
/// - Resets the navigation stack and navigates to [WelcomeScreen]
/// - Does not close the application
/// - Preserves registered users, shops, customers, and transaction records
Future<bool> showLogoutConfirmationDialog({
  required BuildContext context,
  required QboxStore store,
  ApiService? apiService,
}) async {
  final shouldLogout = await showDialog<bool>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: const Text('Logout'),
      content: const Text('Are you sure you want to log out?'),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(ctx, false),
          child: const Text('Cancel'),
        ),
        FilledButton(
          style: FilledButton.styleFrom(
            backgroundColor: const Color(0xFF176B5B),
          ),
          onPressed: () => Navigator.pop(ctx, true),
          child: const Text('Logout'),
        ),
      ],
    ),
  );

  if (shouldLogout == true && context.mounted) {
    store.logout(apiService: apiService);
    Navigator.pushAndRemoveUntil(
      context,
      MaterialPageRoute(builder: (_) => WelcomeScreen(store: store)),
      (route) => false,
    );
    return true;
  }
  return false;
}

