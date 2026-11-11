/// Represents a registered shopkeeper in the local demo session or backend database.
class ShopkeeperProfile {
  ShopkeeperProfile({
    required this.fullName,
    required this.shopName,
    required this.shopAddress,
    required this.phone,
    this.email,
    this.upiId,
    this.qrCodeName,
    this.userId,
    this.shopId,
    this.accessToken,
    this.refreshToken,
    this.paymentQrUrl,
    this.hasPaymentQr = false,
  });

  final String fullName;
  final String shopName;
  final String shopAddress;
  final String phone;
  final String? email;
  final String? upiId;
  final String? qrCodeName;
  final String? userId;
  final String? shopId;
  final String? accessToken;
  final String? refreshToken;
  final String? paymentQrUrl;
  final bool hasPaymentQr;

  bool get hasQrCode => (qrCodeName != null && qrCodeName!.isNotEmpty) || hasPaymentQr;
}

/// Represents a registered customer in the local demo session or backend database.
class RegisteredCustomer {
  RegisteredCustomer({
    required this.fullName,
    required this.phone,
    required this.address,
    this.userId,
    this.accessToken,
    this.refreshToken,
  });

  final String fullName;
  final String phone;
  final String address;
  final String? userId;
  final String? accessToken;
  final String? refreshToken;
}

/// Active registration QR metadata and code for a shopkeeper's shop.
class ShopRegistrationQrData {
  ShopRegistrationQrData({
    required this.shopId,
    required this.shopName,
    required this.shopAddress,
    required this.registrationUrl,
    required this.qrCodeSvg,
    required this.isActive,
    required this.createdAt,
  });

  final String shopId;
  final String shopName;
  final String shopAddress;
  final String registrationUrl;
  final String qrCodeSvg;
  final bool isActive;
  final String createdAt;

  factory ShopRegistrationQrData.fromJson(Map<String, dynamic> json) {
    return ShopRegistrationQrData(
      shopId: json['shop_id']?.toString() ?? '',
      shopName: json['shop_name'] as String? ?? '',
      shopAddress: json['shop_address'] as String? ?? '',
      registrationUrl: json['registration_url'] as String? ?? '',
      qrCodeSvg: json['qr_code_svg'] as String? ?? '',
      isActive: json['is_active'] as bool? ?? true,
      createdAt: json['created_at'] as String? ?? '',
    );
  }
}

/// Public verified shop info returned upon scanning/resolving a registration token.
class PublicShopInfo {
  PublicShopInfo({
    required this.shopId,
    required this.shopName,
    required this.shopAddress,
    required this.token,
  });

  final String shopId;
  final String shopName;
  final String shopAddress;
  final String token;

  factory PublicShopInfo.fromJson(Map<String, dynamic> json, String token) {
    return PublicShopInfo(
      shopId: json['shop_id']?.toString() ?? '',
      shopName: json['shop_name'] as String? ?? '',
      shopAddress: json['shop_address'] as String? ?? '',
      token: token,
    );
  }
}

/// A shop that a customer has joined.
class CustomerJoinedShop {
  CustomerJoinedShop({
    required this.shopId,
    required this.shopName,
    required this.shopAddress,
    required this.joinedAt,
    required this.status,
  });

  final String shopId;
  final String shopName;
  final String shopAddress;
  final String joinedAt;
  final String status;

  factory CustomerJoinedShop.fromJson(Map<String, dynamic> json) {
    return CustomerJoinedShop(
      shopId: json['shop_id']?.toString() ?? '',
      shopName: json['shop_name'] as String? ?? '',
      shopAddress: json['shop_address'] as String? ?? '',
      joinedAt: json['joined_at'] as String? ?? '',
      status: json['status'] as String? ?? 'ACTIVE',
    );
  }
}

/// A customer displayed in a shopkeeper's onboarding directory.
class ShopCustomerItem {
  ShopCustomerItem({
    required this.customerId,
    required this.fullName,
    required this.phone,
    this.address,
    required this.joinedAt,
    required this.status,
    this.currentBalancePaise = 0,
  });

  final String customerId;
  final String fullName;
  final String phone;
  final String? address;
  final String joinedAt;
  final String status;
  final int currentBalancePaise;

  factory ShopCustomerItem.fromJson(Map<String, dynamic> json) {
    return ShopCustomerItem(
      customerId: (json['customer_id'] ?? json['customer_user_id'])?.toString() ?? '',
      fullName: json['full_name'] as String? ?? '',
      phone: json['phone'] as String? ?? '',
      address: json['address'] as String?,
      joinedAt: json['joined_at'] as String? ?? '',
      status: json['status'] as String? ?? 'ACTIVE',
      currentBalancePaise: (json['current_balance_paise'] as num?)?.toInt() ?? 0,
    );
  }
}

/// Static UPI Payment QR details retrieved by a connected customer.
class CustomerShopPaymentQr {
  CustomerShopPaymentQr({
    required this.shopId,
    required this.shopName,
    this.upiId,
    required this.hasPaymentQr,
    this.paymentQrUrl,
    this.upiProvider,
    required this.disclaimer,
  });

  final String shopId;
  final String shopName;
  final String? upiId;
  final bool hasPaymentQr;
  final String? paymentQrUrl;
  final String? upiProvider;
  final String disclaimer;

  factory CustomerShopPaymentQr.fromJson(Map<String, dynamic> json) {
    return CustomerShopPaymentQr(
      shopId: json['shop_id']?.toString() ?? '',
      shopName: json['shop_name'] as String? ?? '',
      upiId: json['upi_id'] as String?,
      hasPaymentQr: json['has_payment_qr'] as bool? ?? false,
      paymentQrUrl: json['payment_qr_url'] as String?,
      upiProvider: json['upi_provider'] as String?,
      disclaimer: json['disclaimer'] as String? ??
          'Scan or pay using any UPI app (GPay, PhonePe, Paytm, BHIM). Qbox does not hold or process customer funds; payments are made directly to the merchant.',
    );
  }
}

/// Static UPI Payment QR metadata for shopkeeper management.
class ShopPaymentQrMeta {
  ShopPaymentQrMeta({
    required this.id,
    required this.shopId,
    required this.originalFilename,
    required this.contentType,
    required this.fileSizeBytes,
    this.upiProvider,
    required this.imageUrl,
    required this.isActive,
    required this.createdAt,
    required this.updatedAt,
  });

  final String id;
  final String shopId;
  final String originalFilename;
  final String contentType;
  final int fileSizeBytes;
  final String? upiProvider;
  final String imageUrl;
  final bool isActive;
  final String createdAt;
  final String updatedAt;

  factory ShopPaymentQrMeta.fromJson(Map<String, dynamic> json) {
    return ShopPaymentQrMeta(
      id: json['id']?.toString() ?? '',
      shopId: json['shop_id']?.toString() ?? '',
      originalFilename: json['original_filename'] as String? ?? '',
      contentType: json['content_type'] as String? ?? 'image/png',
      fileSizeBytes: json['file_size_bytes'] as int? ?? 0,
      upiProvider: json['upi_provider'] as String?,
      imageUrl: json['image_url'] as String? ?? '',
      isActive: json['is_active'] as bool? ?? true,
      createdAt: json['created_at'] as String? ?? '',
      updatedAt: json['updated_at'] as String? ?? '',
    );
  }
}
