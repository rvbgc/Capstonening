import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:image_picker/image_picker.dart';

class ScreenshotInput extends StatefulWidget {
  const ScreenshotInput({
    super.key,
    required this.onTextExtracted,
    required this.onBusyChanged,
    this.enabled = true,
  });

  final ValueChanged<String> onTextExtracted;
  final ValueChanged<bool> onBusyChanged;
  final bool enabled;

  @override
  State<ScreenshotInput> createState() => _ScreenshotInputState();
}

class _ScreenshotInputState extends State<ScreenshotInput> {
  final _picker = ImagePicker();

  bool _busy = false;
  String? _status;

  Future<void> _selectScreenshot() async {
    if (_busy || !widget.enabled) return;

    setState(() {
      _busy = true;
      _status = null;
    });
    widget.onBusyChanged(true);

    http.Client? client;

    try {
      final selected = await _picker.pickImage(
        source: ImageSource.gallery,
      );

      if (selected == null || !mounted) return;

      final name = selected.name.toLowerCase();

      if (!(name.endsWith('.png') ||
          name.endsWith('.jpg') ||
          name.endsWith('.jpeg'))) {
        setState(() {
          _status = 'Choose a PNG or JPEG screenshot.';
        });
        return;
      }

      if (await selected.length() > 5 * 1024 * 1024) {
        if (!mounted) return;
        setState(() {
          _status = 'Choose a screenshot no larger than 5 MB.';
        });
        return;
      }

      if (!mounted) return;

      final confirmed = await showDialog<bool>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: const Text('Extract screenshot text?'),
          content: const Text(
            'This image will be sent to the server for text extraction. '
            'Remove unrelated conversations, OTPs, passwords, and '
            'account details first.\n\n'
            'Extracted text will replace the current message. '
            'You can review and correct it before analysis.',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext, false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(dialogContext, true),
              child: const Text('Extract text'),
            ),
          ],
        ),
      );

      if (confirmed != true || !mounted) return;

      setState(() {
        _status = 'Uploading screenshot and extracting text...';
      });

      final bytes = await selected.readAsBytes();

      if (bytes.isEmpty || bytes.length > 5 * 1024 * 1024) {
        if (!mounted) return;
        setState(() {
          _status = 'The screenshot is empty or exceeds 5 MB.';
        });
        return;
      }

      client = http.Client();

      final request = http.MultipartRequest(
        'POST',
        Uri.parse('http://10.0.2.2:8000/ocr'),
      );

      request.files.add(
        http.MultipartFile.fromBytes(
          'file',
          bytes,
          filename: selected.name,
        ),
      );

      final response = await client
          .send(request)
          .then(http.Response.fromStream)
          .timeout(const Duration(seconds: 35));

      if (!mounted) return;

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        final text = data is Map<String, dynamic> ? data['text'] : null;

        if (text is! String ||
            text.trim().isEmpty ||
            text.length > 5000) {
          setState(() {
            _status = 'No usable text was returned. Try another screenshot.';
          });
          return;
        }

        widget.onTextExtracted(text.trim());

        setState(() {
          _status =
              'Text extracted. Check the words and links below '
              'before tapping Analyze Message.';
        });
      } else {
        final messages = {
          400: 'The uploaded file is empty.',
          413: 'The image is too large. Crop it and try again.',
          415: 'Use a single, non-animated PNG or JPEG image.',
          422: 'Text could not be extracted. Crop to one clear message.',
          429: 'OCR is busy. Please try again shortly.',
          503: 'The OCR service is unavailable.',
          504: 'OCR timed out. Try a smaller crop.',
        };

        setState(() {
          _status = messages[response.statusCode] ??
              'Screenshot processing failed. Please try again.';
        });
      }
    } on TimeoutException {
      if (mounted) {
        setState(() {
          _status = 'The upload or OCR request timed out. Please retry.';
        });
      }
    } catch (_) {
      if (mounted) {
        setState(() {
          _status =
              'Could not process the screenshot. '
              'Check that the server is running and try again.';
        });
      }
    } finally {
      client?.close();

      if (mounted) {
        setState(() {
          _busy = false;
        });
        widget.onBusyChanged(false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        OutlinedButton.icon(
          onPressed:
              _busy || !widget.enabled ? null : _selectScreenshot,
          icon: const Icon(Icons.image_outlined),
          label: Text(_busy ? 'Processing...' : 'Select screenshot'),
        ),
        if (_status != null) ...[
          const SizedBox(height: 8),
          Semantics(
            liveRegion: true,
            child: Text(_status!),
          ),
        ],
        const SizedBox(height: 16),
      ],
    );
  }
}