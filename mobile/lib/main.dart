import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import 'account_screen.dart';
import 'account_service.dart';
import 'api_config.dart';
import 'backend_status.dart';
import 'screenshot_input.dart';

void main() {
  runApp(const SmishGuardApp());
}

class SmishGuardApp extends StatelessWidget {
  const SmishGuardApp({super.key, this.client});

  final http.Client? client;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'SMISHGUARD',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.teal),
        useMaterial3: true,
      ),
      home: MessageScreen(client: client),
    );
  }
}

class MessageScreen extends StatefulWidget {
  const MessageScreen({super.key, this.client});

  final http.Client? client;

  @override
  State<MessageScreen> createState() => _MessageScreenState();
}

/// A successful analysis, split into the SMS model result and the
/// separate PhishHunt URL check.
class _Assessment {
  const _Assessment({
    required this.flagged,
    required this.smsHeading,
    required this.smsBody,
    required this.urlMatched,
    required this.urlHeading,
    required this.urlBody,
    this.saveNote,
  });

  final bool flagged;
  final String smsHeading;
  final String smsBody;
  final bool urlMatched;
  final String urlHeading;
  final String urlBody;
  final String? saveNote;
}

class _MessageScreenState extends State<MessageScreen> {
  final _messageController = TextEditingController();
  late final http.Client _client;
  late final AccountService _account;

  String? _error;

  /// Status or error message shown when no assessment was made.
  String? _result;

  /// Successful analysis, shown as two separate cards.
  _Assessment? _assessment;

  bool _loading = false;
  bool _ocrLoading = false;
  bool _reporting = false;
  bool _saveHistory = false;
  bool _accountOpening = false;
  String _inputMethod = 'text';
  String? _reportResult;

  @override
  void initState() {
    super.initState();
    _client = widget.client ?? http.Client();
    _account = AccountService(client: _client);
  }

  @override
  void dispose() {
    _messageController.dispose();

    if (widget.client == null) {
      _client.close();
    }

    super.dispose();
  }

  Future<void> _openAccount() async {
    if (_loading || _ocrLoading || _reporting || _accountOpening) return;

    FocusScope.of(context).unfocus();

    final previousUserId = _account.userId;

    setState(() => _accountOpening = true);

    try {
      await Navigator.of(context).push<void>(
        MaterialPageRoute(
          builder: (_) => AccountScreen(account: _account),
        ),
      );
    } finally {
      if (mounted) {
        setState(() {
          _accountOpening = false;

          if (!_account.isSignedIn || previousUserId != _account.userId) {
            _saveHistory = false;
          }

          if (previousUserId != null && previousUserId != _account.userId) {
            _messageController.clear();
            _inputMethod = 'text';
            _error = null;
            _result = null;
            _assessment = null;
            _reportResult = null;
          }
        });
      }
    }
  }

  Future<void> _reportMessage() async {
    if (_loading || _ocrLoading || _reporting) return;

    final text = _messageController.text.trim();
    final inputMethod = _inputMethod;

    if (text.isEmpty || text.runes.length > 5000) {
      setState(() {
        _error = 'Enter one message containing 1–5,000 characters.';
      });
      return;
    }

    FocusScope.of(context).unfocus();

    setState(() {
      _reporting = true;
      _reportResult = null;
      _error = null;
    });

    String? notice;

    try {
      final consent = await showDialog<bool>(
        context: context,
        builder: (dialogContext) {
          return AlertDialog(
            key: const ValueKey('report-consent-dialog'),
            title: const Text('Submit this message?'),
            content: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'The message text below will be sent to SMISHGUARD '
                    'and stored with the model assessment, when available, '
                    'for review. Remove passwords, OTPs, account details, '
                    'and unnecessary personal information first.',
                  ),
                  const SizedBox(height: 16),
                  Text(text),
                  const SizedBox(height: 16),
                  const Text(
                    'The original screenshot is not included in this report. '
                    'Submitting a report does not confirm that the message '
                    'is smishing.',
                  ),
                ],
              ),
            ),
            actions: [
              TextButton(
                key: const ValueKey('cancel-report-button'),
                onPressed: () => Navigator.of(dialogContext).pop(false),
                child: const Text('Cancel'),
              ),
              FilledButton(
                key: const ValueKey('confirm-report-button'),
                onPressed: () => Navigator.of(dialogContext).pop(true),
                child: const Text('Submit report'),
              ),
            ],
          );
        },
      );

      if (!mounted || consent != true) return;

      final response = await _client
          .post(
            Uri.parse('$apiBaseUrl/reports'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'text': text,
              'input_method': inputMethod,
              'consent': true,
            }),
          )
          .timeout(const Duration(seconds: 15));

      if (response.statusCode == 201) {
        final data = jsonDecode(response.body);

        if (data is! Map<String, dynamic>) {
          throw const FormatException('Invalid report response.');
        }

        final reportId = data['report_id'];

        if (reportId is! String ||
            reportId.trim().isEmpty ||
            data['review_status'] != 'pending') {
          throw const FormatException('Invalid report receipt.');
        }

        notice = 'Report submitted.\n\n'
            'Status: Pending review\n'
            'Report ID: $reportId\n\n'
            'This report has not been verified.';
      } else if (response.statusCode == 422) {
        notice = 'The report was rejected. Check the message and try again.';
      } else {
        notice = 'Report submission could not be confirmed. '
            'Check the server before trying again.';
      }
    } on TimeoutException {
      notice = 'The request timed out. Your report may have been saved. '
          'Check before submitting it again.';
    } on http.ClientException {
      notice = 'The server connection failed. '
          'Report submission was not confirmed.';
    } catch (_) {
      notice = 'The response could not be processed. '
          'Report submission was not confirmed.';
    } finally {
      if (mounted) {
        setState(() {
          _reporting = false;
          if (notice != null) {
            _reportResult = notice;
          }
        });
      }
    }
  }

  Future<void> _analyze() async {
    if (_loading || _ocrLoading || _reporting) return;

    final saveRequested = _saveHistory;
    final sessionToken = _account.token;

    if (saveRequested && !_account.isSignedIn) {
      setState(() {
        _saveHistory = false;
        _error = 'Sign in before saving an analysis.';
      });
      return;
    }

    final text = _messageController.text.trim();

    if (text.isEmpty) {
      setState(() {
        _error = 'Enter a message first.';
        _result = null;
        _assessment = null;
      });
      return;
    }

    FocusScope.of(context).unfocus();

    setState(() {
      _error = null;
      _result = null;
      _assessment = null;
      _loading = true;
    });

    String? result;
    _Assessment? assessment;

    try {
      final response = await _client
          .post(
            Uri.parse('${AccountService.baseUrl}/analyze'),
            headers: {
              'Content-Type': 'application/json',
              if (saveRequested && sessionToken != null)
                'Authorization': 'Bearer $sessionToken',
            },
            body: jsonEncode({
              'text': text,
              if (saveRequested) 'save_history': true,
              if (saveRequested) 'input_method': _inputMethod,
            }),
          )
          .timeout(const Duration(seconds: 30));

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);

        if (data is! Map<String, dynamic>) {
          throw const FormatException('Invalid response format.');
        }

        final label = data['label'];
        final message = data['message'];

        if (message is! String || message.trim().isEmpty) {
          throw const FormatException('Missing assessment message.');
        }

        if (label != 'smishing' && label != 'non_smishing') {
          throw const FormatException('Unknown classification label.');
        }

        final flagged = label == 'smishing';

        const urlHeadings = <String, String>{
          'matched': 'URL match in the PhishHunt feed',
          'not_listed': 'No URL match in the PhishHunt feed',
          'no_urls': 'No complete web link recognized',
          'stale': 'URL check unavailable: outdated threat data',
          'unavailable': 'URL check unavailable',
          'not_checked': 'URLs were not checked',
          'incomplete': 'URL check incomplete',
        };

        var urlHeading = 'URL check unavailable';
        var urlMessage = 'No usable URL-check result was received. '
            'The safety of any links has not been established.';
        var urlMatched = false;

        final threatInfo = data['threat_intelligence'];

        if (threatInfo is Map<String, dynamic> &&
            threatInfo['source'] == 'PhishHunt') {
          final urlStatus = threatInfo['status'];
          final backendUrlMessage = threatInfo['message'];

          if (urlStatus is String &&
              urlHeadings.containsKey(urlStatus) &&
              backendUrlMessage is String &&
              backendUrlMessage.trim().isNotEmpty) {
            urlHeading = urlHeadings[urlStatus]!;
            urlMessage = backendUrlMessage.trim();
            urlMatched = urlStatus == 'matched';
          }
        }

        String? saveNote;

        if (saveRequested) {
          final history = data['history'];

          if (history is Map<String, dynamic> &&
              history['status'] == 'saved') {
            saveNote = 'Saved to your private history.';
          } else {
            saveNote = 'Saving could not be confirmed. '
                'Check your history before retrying.';
          }
        }

        assessment = _Assessment(
          flagged: flagged,
          smsHeading:
              flagged ? 'Possible smishing detected' : 'Smishing not detected',
          smsBody: message.trim(),
          urlMatched: urlMatched,
          urlHeading: urlHeading,
          urlBody: urlMessage,
          saveNote: saveNote,
        );
      } else if (response.statusCode == 401) {
        await _account.forgetSession();

        if (mounted) {
          setState(() => _saveHistory = false);
        }

        result =
            'Your session has expired. Sign in again before saving an analysis.';
      } else if (response.statusCode == 503) {
        final data = jsonDecode(response.body);
        final detail = data is Map<String, dynamic> ? data['detail'] : null;

        if (detail is Map<String, dynamic> &&
            detail['code'] == 'MODEL_NOT_READY') {
          result = 'The server received your message. '
              'Detection is not available yet. '
              'No risk assessment was made.';
        } else {
          result = 'Analysis is temporarily unavailable. Try again later.';
        }
      } else if (response.statusCode == 422) {
        result = 'The server rejected the submission. '
            'Enter one message containing 1–5,000 characters.';
      } else {
        result = 'The server returned an unexpected response. '
            'No assessment is available.';
      }
    } on TimeoutException {
      assessment = null;
      result = saveRequested
          ? 'The request timed out. Saving could not be confirmed. '
              'Check your history before retrying.'
          : 'The request timed out. No assessment was received.';
    } on http.ClientException {
      assessment = null;
      result = saveRequested
          ? 'The connection was interrupted. Saving could not be confirmed. '
              'Check your history before retrying.'
          : 'Cannot reach the server. Check your connection and retry.';
    } catch (_) {
      assessment = null;
      result = saveRequested
          ? 'The response could not be processed. Saving could not be '
              'confirmed. Check your history before retrying.'
          : 'The response could not be processed. '
              'No assessment is available.';
    }

    if (!mounted) return;

    setState(() {
      _loading = false;
      _result = result;
      _assessment = assessment;
    });
  }

  // ---------------------------------------------------------------------------
  // UI helpers
  // ---------------------------------------------------------------------------

  /// A titled section card used for the input and report areas.
  Widget _section({
    required IconData icon,
    required String title,
    String? subtitle,
    required Widget child,
  }) {
    final theme = Theme.of(context);

    return Card(
      margin: EdgeInsets.zero,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, color: theme.colorScheme.primary),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(title, style: theme.textTheme.titleMedium),
                ),
              ],
            ),
            if (subtitle != null) ...[
              const SizedBox(height: 4),
              Text(subtitle, style: theme.textTheme.bodySmall),
            ],
            const SizedBox(height: 12),
            child,
          ],
        ),
      ),
    );
  }

  /// A result card with a title, a bold finding and explanatory text.
  /// [highlight] uses the error colours for findings that need attention.
  Widget _findingCard({
    required Key key,
    required IconData icon,
    required String title,
    required String heading,
    required String body,
    List<String> notes = const [],
    bool highlight = false,
  }) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final foreground = highlight ? scheme.onErrorContainer : null;

    return Card(
      key: key,
      margin: EdgeInsets.zero,
      color: highlight ? scheme.errorContainer : null,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Semantics(
          liveRegion: true,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(icon, color: foreground ?? scheme.primary),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      title,
                      style: theme.textTheme.labelLarge
                          ?.copyWith(color: foreground),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Text(
                heading,
                style: theme.textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.bold,
                  color: foreground,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                body,
                style: theme.textTheme.bodyMedium?.copyWith(color: foreground),
              ),
              for (final note in notes) ...[
                const SizedBox(height: 8),
                Text(
                  note,
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: foreground,
                    fontStyle: FontStyle.italic,
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  /// A plain card for status, error and report messages.
  Widget _messageCard(String text, {Key? key}) {
    return Card(
      key: key,
      margin: EdgeInsets.zero,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Semantics(
          liveRegion: true,
          child: Text(text),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final busy = _loading || _ocrLoading || _reporting;
    final signedIn = _account.isSignedIn;
    final assessment = _assessment;

    return Scaffold(
      appBar: AppBar(
        title: const Text('SMISHGUARD'),
        centerTitle: true,
        actions: [
          IconButton(
            key: const ValueKey('account-button'),
            tooltip: signedIn
                ? 'Account and history (signed in)'
                : 'Account and history',
            onPressed: (busy || _accountOpening) ? null : _openAccount,
            icon: Badge(
              isLabelVisible: signedIn,
              child: Icon(
                signedIn
                    ? Icons.account_circle
                    : Icons.account_circle_outlined,
              ),
            ),
          ),
        ],
      ),
      body: SafeArea(
        child: GestureDetector(
          // Tapping empty space closes the keyboard.
          behavior: HitTestBehavior.translucent,
          onTap: () => FocusScope.of(context).unfocus(),
          child: ListView(
            keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
            children: [
              BackendStatus(client: _client),
              const SizedBox(height: 8),

              // ---------------- Header ----------------
              Row(
                children: [
                  Icon(
                    Icons.shield_outlined,
                    size: 40,
                    color: theme.colorScheme.primary,
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      'Check a suspicious message',
                      style: theme.textTheme.headlineSmall,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              const Text(
                'Type or paste an English SMS below. '
                'Remove passwords, OTPs, and account details first.',
              ),
              const SizedBox(height: 20),

              // ---------------- Screenshot input ----------------
              _section(
                icon: Icons.image_outlined,
                title: 'Upload a screenshot (optional)',
                subtitle: 'The text found in the screenshot is placed in '
                    'the message box below for you to review and edit.',
                child: ScreenshotInput(
                  enabled: !_loading && !_reporting,
                  onBusyChanged: (busy) {
                    if (!mounted) return;

                    setState(() {
                      _ocrLoading = busy;
                    });
                  },
                  onTextExtracted: (text) {
                    if (!mounted) return;

                    setState(() {
                      _messageController.text = text;
                      _inputMethod = 'screenshot';
                      _error = null;
                      _result = null;
                      _assessment = null;
                      _reportResult = null;
                    });
                  },
                ),
              ),
              const SizedBox(height: 16),

              // ---------------- Typed input + analyze ----------------
              _section(
                icon: Icons.sms_outlined,
                title: 'Message text',
                subtitle: _inputMethod == 'screenshot'
                    ? 'Extracted from your screenshot. Check that it '
                        'matches the original message.'
                    : 'Type or paste the message you received.',
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    TextField(
                      controller: _messageController,
                      readOnly: busy,
                      minLines: 6,
                      maxLines: 12,
                      maxLength: 5000,
                      keyboardType: TextInputType.multiline,
                      onChanged: (value) {
                        setState(() {
                          if (value.trim().isEmpty) {
                            _inputMethod = 'text';
                          }

                          _error = null;
                          _result = null;
                          _assessment = null;
                          _reportResult = null;
                        });
                      },
                      decoration: InputDecoration(
                        labelText: 'SMS message',
                        hintText: 'Paste the message here...',
                        alignLabelWithHint: true,
                        border: const OutlineInputBorder(),
                        errorText: _error,
                      ),
                    ),
                    if (signedIn)
                      CheckboxListTile(
                        key: const ValueKey('save-history-checkbox'),
                        contentPadding: EdgeInsets.zero,
                        controlAffinity: ListTileControlAffinity.leading,
                        title: const Text('Save this analysis to my history'),
                        subtitle: const Text(
                          'Saves the message and result to your account when '
                          'you tap Analyze. Your latest 100 saved analyses '
                          'are retained.',
                        ),
                        value: _saveHistory,
                        onChanged: busy
                            ? null
                            : (value) {
                                setState(() {
                                  _saveHistory = value ?? false;
                                });
                              },
                      ),
                    const SizedBox(height: 8),
                    FilledButton.icon(
                      key: const ValueKey('analyze-message-button'),
                      onPressed: busy ? null : _analyze,
                      style: FilledButton.styleFrom(
                        minimumSize: const Size.fromHeight(48),
                      ),
                      icon: _loading
                          ? const SizedBox(
                              width: 18,
                              height: 18,
                              child:
                                  CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Icon(Icons.search),
                      label: Text(
                        _loading ? 'Submitting...' : 'Analyze Message',
                      ),
                    ),
                    if (_loading) ...[
                      const SizedBox(height: 8),
                      Text(
                        'Checking the message and any links. '
                        'This can take up to 30 seconds.',
                        style: theme.textTheme.bodySmall,
                        textAlign: TextAlign.center,
                      ),
                    ],
                    if (_ocrLoading) ...[
                      const SizedBox(height: 8),
                      Text(
                        'Reading text from the screenshot...',
                        style: theme.textTheme.bodySmall,
                        textAlign: TextAlign.center,
                      ),
                    ],
                  ],
                ),
              ),

              // ---------------- Results ----------------
              if (assessment != null) ...[
                const SizedBox(height: 24),
                Text('Results', style: theme.textTheme.titleLarge),
                const SizedBox(height: 8),
                _findingCard(
                  key: const ValueKey('sms-assessment-card'),
                  icon: assessment.flagged
                      ? Icons.warning_amber_rounded
                      : Icons.sms_outlined,
                  title: 'SMS assessment',
                  heading: assessment.smsHeading,
                  body: assessment.smsBody,
                  highlight: assessment.flagged,
                  notes: [
                    'Preliminary prototype result. The model can be wrong.',
                    if (assessment.saveNote != null) assessment.saveNote!,
                  ],
                ),
                const SizedBox(height: 12),
                _findingCard(
                  key: const ValueKey('url-check-card'),
                  icon: assessment.urlMatched
                      ? Icons.dangerous_outlined
                      : Icons.link,
                  title: 'URL check (PhishHunt)',
                  heading: assessment.urlHeading,
                  body: assessment.urlBody,
                  highlight: assessment.urlMatched,
                ),
              ],
              if (_result != null) ...[
                const SizedBox(height: 24),
                _messageCard(_result!, key: const ValueKey('status-card')),
              ],

              // ---------------- Report ----------------
              const SizedBox(height: 24),
              _section(
                icon: Icons.flag_outlined,
                title: 'Report this message',
                subtitle: 'Send it to SMISHGUARD for review. '
                    'Reports stay pending until reviewed.',
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    OutlinedButton.icon(
                      key: const ValueKey('report-message-button'),
                      onPressed:
                          (busy || _messageController.text.trim().isEmpty)
                              ? null
                              : _reportMessage,
                      icon: _reporting
                          ? const SizedBox(
                              width: 18,
                              height: 18,
                              child:
                                  CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Icon(Icons.flag_outlined),
                      label: Text(
                        _reporting ? 'Please wait...' : 'Report Message',
                      ),
                    ),
                    if (_reportResult != null) ...[
                      const SizedBox(height: 12),
                      _messageCard(
                        _reportResult!,
                        key: const ValueKey('report-result-card'),
                      ),
                    ],
                  ],
                ),
              ),

              // ---------------- Footer ----------------
              const SizedBox(height: 24),
              Text(
                'Prototype results may be incorrect. '
                'Verify suspicious messages through official channels.',
                textAlign: TextAlign.center,
                style: theme.textTheme.bodySmall,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
