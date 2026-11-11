/// Input validation utilities for Qbox forms.
class Validators {
  /// Strips formatting characters, spaces, and country code from phone numbers.
  static String normalizePhone(String raw) {
    var cleaned = raw.replaceAll(RegExp(r'[\s\-\(\)]'), '');
    if (cleaned.startsWith('+91')) {
      cleaned = cleaned.substring(3);
    } else if (cleaned.startsWith('91') && cleaned.length == 12) {
      cleaned = cleaned.substring(2);
    } else if (cleaned.startsWith('0') && cleaned.length == 11) {
      cleaned = cleaned.substring(1);
    }
    return cleaned;
  }

  /// Validates required text fields.
  static String? validateRequired(
    String? value,
    String fieldName, {
    int minLength = 2,
  }) {
    if (value == null || value.trim().isEmpty) {
      return '$fieldName is required';
    }
    if (value.trim().length < minLength) {
      return '$fieldName must be at least $minLength characters';
    }
    return null;
  }

  /// Validates standard 10-digit Indian mobile numbers starting with 6, 7, 8, or 9.
  static String? validatePhone(String? value) {
    if (value == null || value.trim().isEmpty) {
      return 'Phone number is required';
    }
    final normalized = normalizePhone(value);
    if (!RegExp(r'^[6-9]\d{9}$').hasMatch(normalized)) {
      return 'Enter a valid 10-digit mobile number (starts with 6-9)';
    }
    return null;
  }

  /// Validates UPI ID format (e.g. name@upi, 9876543210@paytm).
  /// UPI ID is optional; returns null if empty.
  static String? validateUpi(String? value) {
    if (value == null || value.trim().isEmpty) {
      return null; // UPI ID is optional
    }
    final trimmed = value.trim();
    // Standard UPI ID pattern: user@bankhandle
    final upiRegex = RegExp(r'^[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z]{2,64}$');
    if (!upiRegex.hasMatch(trimmed)) {
      return 'Enter a valid UPI ID (e.g. shopname@upi or 9876543210@paytm)';
    }
    return null;
  }

  /// Validates password strength (minimum 8 characters).
  static String? validatePassword(String? value) {
    if (value == null || value.isEmpty) {
      return 'Password is required';
    }
    if (value.length < 8) {
      return 'Password must be at least 8 characters';
    }
    return null;
  }
}

