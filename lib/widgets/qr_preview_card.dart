import 'dart:typed_data';
import 'package:flutter/material.dart';

/// Interactive preview card for shopkeeper payment QR code.
class QrPreviewCard extends StatelessWidget {
  const QrPreviewCard({
    super.key,
    required this.qrName,
    required this.shopName,
    this.upiId,
    this.imageBytes,
    this.fileSizeBytes,
    this.provider,
    required this.onChange,
    required this.onRemove,
    this.replaceLabel = 'Replace QR',
  });

  final String qrName;
  final String shopName;
  final String? upiId;
  final Uint8List? imageBytes;
  final int? fileSizeBytes;
  final String? provider;
  final VoidCallback onChange;
  final VoidCallback onRemove;
  final String replaceLabel;

  String _formatSize(int bytes) {
    if (bytes < 1024) return '$bytes B';
    if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(1)} KB';
    return '${(bytes / (1024 * 1024)).toStringAsFixed(2)} MB';
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFF176B5B), width: 1.5),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.04),
            blurRadius: 8,
            offset: const Offset(0, 3),
          ),
        ],
      ),
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Row(
            children: [
              const Icon(
                Icons.check_circle,
                color: Color(0xFF176B5B),
                size: 20,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      qrName,
                      style: const TextStyle(
                        fontWeight: FontWeight.bold,
                        fontSize: 14,
                        color: Color(0xFF176B5B),
                      ),
                      overflow: TextOverflow.ellipsis,
                    ),
                    if (fileSizeBytes != null)
                      Text(
                        _formatSize(fileSizeBytes!),
                        style: const TextStyle(
                          fontSize: 11,
                          color: Colors.black54,
                        ),
                      ),
                  ],
                ),
              ),
              IconButton(
                icon: const Icon(Icons.close, size: 20, color: Colors.black54),
                onPressed: onRemove,
                tooltip: 'Remove QR',
                constraints: const BoxConstraints(),
                padding: EdgeInsets.zero,
              ),
            ],
          ),
          const SizedBox(height: 12),
          // QR Code Graphic Container
          Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: Colors.black12),
            ),
            child: Column(
              children: [
                if (imageBytes != null)
                  ClipRRect(
                    borderRadius: BorderRadius.circular(8),
                    child: SizedBox(
                      width: 160,
                      height: 160,
                      child: Image.memory(
                        imageBytes!,
                        fit: BoxFit.contain,
                        errorBuilder: (context, error, stackTrace) => Container(
                          color: const Color(0xFFF3F4F6),
                          child: const Center(
                            child: Icon(
                              Icons.qr_code,
                              size: 80,
                              color: Color(0xFF176B5B),
                            ),
                          ),
                        ),
                      ),
                    ),
                  )
                else
                  SizedBox(
                    width: 140,
                    height: 140,
                    child: CustomPaint(
                      painter: _QrCodePainter(),
                    ),
                  ),
                const SizedBox(height: 8),
                Text(
                  shopName.isEmpty ? 'Your Shop Name' : shopName,
                  style: const TextStyle(
                    fontWeight: FontWeight.bold,
                    fontSize: 13,
                  ),
                  textAlign: TextAlign.center,
                ),
                if (upiId != null && upiId!.isNotEmpty) ...[
                  const SizedBox(height: 2),
                  Text(
                    'UPI: $upiId',
                    style: const TextStyle(
                      fontSize: 11,
                      color: Colors.black54,
                    ),
                    textAlign: TextAlign.center,
                  ),
                ],
                const SizedBox(height: 4),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(
                    color: const Color(0xFFE2F1ED),
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(Icons.qr_code_scanner, size: 12, color: Color(0xFF176B5B)),
                      const SizedBox(width: 4),
                      Text(
                        provider != null && provider!.isNotEmpty
                            ? '$provider UPI PREVIEW'
                            : 'BHIM UPI PREVIEW',
                        style: const TextStyle(
                          fontSize: 9,
                          fontWeight: FontWeight.bold,
                          color: Color(0xFF176B5B),
                          letterSpacing: 0.5,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              OutlinedButton.icon(
                onPressed: onChange,
                icon: const Icon(Icons.refresh, size: 16),
                label: Text(replaceLabel, style: const TextStyle(fontSize: 12)),
                style: OutlinedButton.styleFrom(
                  visualDensity: VisualDensity.compact,
                ),
              ),
              const SizedBox(width: 12),
              TextButton.icon(
                onPressed: onRemove,
                icon: const Icon(Icons.delete_outline, size: 16, color: Colors.red),
                label: const Text(
                  'Remove',
                  style: TextStyle(fontSize: 12, color: Colors.red),
                ),
                style: TextButton.styleFrom(
                  visualDensity: VisualDensity.compact,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

/// Custom painter to render an authentic QR code pattern with 3 finder eyes.
class _QrCodePainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paintDark = Paint()..color = const Color(0xFF1F2937);
    final paintBrand = Paint()..color = const Color(0xFF176B5B);
    final paintLight = Paint()..color = Colors.white;

    final cellW = size.width / 21;
    final cellH = size.height / 21;

    void drawFinder(double x, double y) {
      // Outer 7x7 box
      canvas.drawRect(
        Rect.fromLTWH(x * cellW, y * cellH, 7 * cellW, 7 * cellH),
        paintDark,
      );
      // Inner 5x5 white cutout
      canvas.drawRect(
        Rect.fromLTWH((x + 1) * cellW, (y + 1) * cellH, 5 * cellW, 5 * cellH),
        paintLight,
      );
      // Center 3x3 solid block
      canvas.drawRect(
        Rect.fromLTWH((x + 2) * cellW, (y + 2) * cellH, 3 * cellW, 3 * cellH),
        paintDark,
      );
    }

    // Three QR finder patterns (top-left, top-right, bottom-left)
    drawFinder(0, 0);
    drawFinder(14, 0);
    drawFinder(0, 14);

    // Timing lines
    for (int i = 8; i <= 12; i++) {
      if (i % 2 == 0) {
        canvas.drawRect(Rect.fromLTWH(6 * cellW, i * cellH, cellW, cellH), paintDark);
        canvas.drawRect(Rect.fromLTWH(i * cellW, 6 * cellH, cellW, cellH), paintDark);
      }
    }

    // Synthetic pseudo-matrix dots for visual realism
    const matrixPattern = [
      0x5A, 0xA5, 0x3C, 0xC3, 0x99, 0x66, 0xAA, 0x55,
      0x33, 0xCC, 0xF0, 0x0F, 0x88, 0x77, 0x22, 0xDD,
      0x44, 0xBB, 0x11, 0xEE, 0x55,
    ];

    for (int r = 0; r < 21; r++) {
      for (int c = 0; c < 21; c++) {
        // Skip finder areas
        if ((r < 8 && c < 8) || (r < 8 && c > 12) || (r > 12 && c < 8)) {
          continue;
        }
        // Center badge area cutout
        if (r >= 8 && r <= 12 && c >= 8 && c <= 12) {
          continue;
        }
        final val = (matrixPattern[r % matrixPattern.length] >> (c % 8)) & 1;
        if (val == 1) {
          canvas.drawRRect(
            RRect.fromRectAndRadius(
              Rect.fromLTWH(c * cellW + 0.5, r * cellH + 0.5, cellW - 1, cellH - 1),
              const Radius.circular(1.5),
            ),
            paintDark,
          );
        }
      }
    }

    // Center Qbox mini badge
    final centerRect = Rect.fromCenter(
      center: Offset(size.width / 2, size.height / 2),
      width: 4 * cellW,
      height: 4 * cellH,
    );
    canvas.drawRRect(
      RRect.fromRectAndRadius(centerRect, const Radius.circular(4)),
      paintLight,
    );
    canvas.drawRRect(
      RRect.fromRectAndRadius(centerRect.deflate(1.5), const Radius.circular(3)),
      paintBrand,
    );
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
