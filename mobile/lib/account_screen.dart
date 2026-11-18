import 'package:flutter/material.dart';

import 'account_service.dart';

class AccountScreen extends StatefulWidget {
  const AccountScreen({super.key, required this.account});

  final AccountService account;

  @override
  State<AccountScreen> createState() => _AccountScreenState();
}

class _AccountScreenState extends State<AccountScreen> {
  final _username = TextEditingController();
  final _password = TextEditingController();

  bool _busy = false;
  bool _registering = false;
  bool _hasMore = false;

  String? _notice;
  List<Map<String, dynamic>> _items = [];
  Map<String, dynamic>? _detail;

  AccountService get account => widget.account;

  @override
  void initState() {
    super.initState();

    _run(() async {
      await account.restore();
      if (account.isSignedIn) {
        await _refresh();
      }
    });
  }

  @override
  void dispose() {
    _username.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _run(Future<void> Function() action) async {
    if (_busy) return;

    setState(() {
      _busy = true;
      _notice = null;
    });

    try {
      await action();
    } on AccountException catch (error) {
      _notice = error.message;
    } catch (_) {
      _notice = 'The operation could not be completed. Please try again.';
    } finally {
      if (mounted) {
        setState(() {
          _busy = false;

          if (!account.isSignedIn) {
            _items = [];
            _detail = null;
            _hasMore = false;
          }
        });
      }
    }
  }

  Future<void> _refresh({bool more = false}) async {
    final data = await account.listHistory(
      offset: more ? _items.length : 0,
    );

    final rawItems = data['items'];

    if (rawItems is! List) {
      throw const AccountException('The history response was invalid.');
    }

    final entries = <Map<String, dynamic>>[];

    for (final item in rawItems) {
      if (item is! Map<String, dynamic> || item['id'] is! String) {
        throw const AccountException('The history response was invalid.');
      }
      entries.add(item);
    }

    _items = more ? [..._items, ...entries] : entries;
    _hasMore = data['has_more'] == true;
  }

  Future<void> _submitAccount() async {
    final username = _username.text.trim().toLowerCase();
    final password = _password.text;

    if (!RegExp(r'^[a-z0-9][a-z0-9_.-]{2,31}$').hasMatch(username)) {
      setState(() {
        _notice = 'Use a username of 3–32 characters: letters, numbers, '
            'underscores, dots, or hyphens. Start with a letter or number.';
      });
      return;
    }

    if (password.isEmpty ||
        password.length > 128 ||
        (_registering && password.length < 12)) {
      setState(() {
        _notice = _registering
            ? 'Use a password containing 12–128 characters.'
            : 'Enter your password.';
      });
      return;
    }

    await _run(() async {
      if (_registering) {
        await account.register(username, password);
        _password.clear();
        _registering = false;
        _notice = 'Account created. Enter your password to sign in.';
      } else {
        await account.login(username, password);
        _password.clear();
        _detail = null;
        _items = [];
        await _refresh();
      }
    });
  }

  Future<bool> _confirm(String title, String message) async {
    return await showDialog<bool>(
          context: context,
          builder: (dialogContext) => AlertDialog(
            title: Text(title),
            content: Text(message),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(dialogContext, false),
                child: const Text('Cancel'),
              ),
              FilledButton(
                onPressed: () => Navigator.pop(dialogContext, true),
                child: const Text('Delete'),
              ),
            ],
          ),
        ) ??
        false;
  }

  Future<void> _deleteAccount() async {
    if (_busy) return;

    final password = await showDialog<String>(
      context: context,
      builder: (_) => const _DeleteAccountDialog(),
    );

    if (password == null || password.isEmpty || !mounted) return;

    await _run(() async {
      await account.deleteAccount(password);
      _username.clear();
      _password.clear();
      _registering = false;
      _notice = 'Your account and all saved analyses were deleted.';
    });
  }

  String _date(dynamic value) {
    final parsed = DateTime.tryParse(value?.toString() ?? '');
    if (parsed == null) return 'Unknown time';

    final local = parsed.toLocal();
    String two(int number) => number.toString().padLeft(2, '0');

    return '${local.year}-${two(local.month)}-${two(local.day)} '
        '${two(local.hour)}:${two(local.minute)}';
  }

  String _label(dynamic value) {
    return switch (value) {
      'smishing' => 'Possible smishing detected',
      'non_smishing' => 'Smishing not detected',
      _ => 'Assessment unavailable',
    };
  }

  Widget _historyDetail() {
    final detail = _detail!;
    final rawResult = detail['analysis_result'];

    final result = rawResult is Map<String, dynamic>
        ? rawResult
        : <String, dynamic>{};

    final rawThreat = result['threat_intelligence'];
    final threat = rawThreat is Map<String, dynamic>
        ? rawThreat
        : <String, dynamic>{};

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        TextButton.icon(
          onPressed: _busy
              ? null
              : () {
                  setState(() => _detail = null);
                },
          icon: const Icon(Icons.arrow_back),
          label: const Text('Back to history'),
        ),
        Text(
          'Saved ${_date(detail['created_at'])}',
          style: Theme.of(context).textTheme.titleMedium,
        ),
        const SizedBox(height: 12),
        const Text(
          'This is the assessment saved at that time. '
          'The message and links have not been checked again.',
        ),
        const SizedBox(height: 16),
        const Text('Message'),
        const SizedBox(height: 8),
        SelectableText(detail['message_text'] as String? ?? ''),
        const Divider(height: 32),
        Text(
          _label(result['label']),
          style: Theme.of(context).textTheme.titleMedium,
        ),
        const SizedBox(height: 8),
        Text(result['message'] as String? ?? 'No assessment message saved.'),
        const SizedBox(height: 20),
        const Text('Saved URL check'),
        const SizedBox(height: 8),
        Text(
          threat['message'] as String? ?? 'No URL-check information saved.',
        ),
        const SizedBox(height: 24),
        OutlinedButton.icon(
          onPressed: _busy
              ? null
              : () => _run(() async {
                    final confirmed = await _confirm(
                      'Delete this entry?',
                      'This removes this saved analysis from your history.',
                    );
                    if (!confirmed) return;

                    final id = detail['id'] as String;
                    await account.deleteHistory(id);

                    _detail = null;
                    _items.removeWhere((item) => item['id'] == id);

                    await _refresh();
                    _notice = 'History entry deleted.';
                  }),
          icon: const Icon(Icons.delete_outline),
          label: const Text('Delete this entry'),
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: !_busy,
      child: Scaffold(
        appBar: AppBar(title: const Text('Account & history')),
        body: ListView(
          padding: const EdgeInsets.all(24),
          children: [
            if (_busy) ...[
              const LinearProgressIndicator(),
              const SizedBox(height: 16),
            ],
            if (_notice != null) ...[
              Text(_notice!),
              const SizedBox(height: 16),
            ],
            if (!account.isSignedIn) ...[
              Text(
                _registering ? 'Create an account' : 'Sign in',
                style: Theme.of(context).textTheme.headlineSmall,
              ),
              const SizedBox(height: 12),
              const Text(
                'Sign in to save and view your private analysis history.',
              ),
              const SizedBox(height: 20),
              TextField(
                controller: _username,
                enabled: !_busy,
                autocorrect: false,
                textCapitalization: TextCapitalization.none,
                maxLength: 32,
                decoration: const InputDecoration(
                  labelText: 'Username',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _password,
                enabled: !_busy,
                obscureText: true,
                autocorrect: false,
                enableSuggestions: false,
                maxLength: 128,
                decoration: InputDecoration(
                  labelText: 'Password',
                  helperText: _registering
                      ? 'Use 12–128 characters.'
                      : null,
                  border: const OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 16),
              FilledButton(
                onPressed: _busy ? null : _submitAccount,
                child: Text(
                  _registering ? 'Create account' : 'Sign in',
                ),
              ),
              TextButton(
                onPressed: _busy
                    ? null
                    : () {
                        setState(() {
                          _registering = !_registering;
                          _notice = null;
                          _password.clear();
                        });
                      },
                child: Text(
                  _registering
                      ? 'Already registered? Sign in'
                      : 'Create an account',
                ),
              ),
              TextButton(
                onPressed: _busy
                    ? null
                    : () => _run(() async {
                          _notice = await account.logout();
                        }),
                child: const Text('Sign out / remove saved session'),
              ),
            ] else ...[
              Text(
                'Signed in as ${account.username}',
                style: Theme.of(context).textTheme.titleMedium,
              ),
              TextButton.icon(
                onPressed: _busy
                    ? null
                    : () => _run(() async {
                          _notice = await account.logout();
                        }),
                icon: const Icon(Icons.logout),
                label: const Text('Sign out'),
              ),
              const Divider(height: 24),
              if (_detail != null)
                _historyDetail()
              else ...[
                const Text(
                  'Only analyses you choose to save appear here. '
                  'Your latest 100 saved analyses are retained.',
                ),
                const SizedBox(height: 12),
                OutlinedButton.icon(
                  onPressed: _busy ? null : () => _run(() => _refresh()),
                  icon: const Icon(Icons.refresh),
                  label: const Text('Refresh history'),
                ),
                if (_items.isEmpty && !_busy)
                  const Padding(
                    padding: EdgeInsets.symmetric(vertical: 24),
                    child: Text('No saved analyses yet.'),
                  ),
                for (final item in _items)
                  Card(
                    child: ListTile(
                      enabled: !_busy,
                      title: Text(
                        item['message_preview'] as String? ?? '',
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                      subtitle: Text(
                        '${_label(item['label'])}\n'
                        '${_date(item['created_at'])}',
                      ),
                      isThreeLine: true,
                      trailing: const Icon(Icons.chevron_right),
                      onTap: () => _run(() async {
                        _detail = await account.openHistory(
                          item['id'] as String,
                        );
                      }),
                    ),
                  ),
                if (_hasMore)
                  TextButton(
                    onPressed: _busy
                        ? null
                        : () => _run(() => _refresh(more: true)),
                    child: const Text('Load more'),
                  ),
                if (_items.isNotEmpty)
                  OutlinedButton.icon(
                    onPressed: _busy
                        ? null
                        : () => _run(() async {
                              final confirmed = await _confirm(
                                'Clear your history?',
                                'This deletes all your saved analyses. '
                                    'Submitted reports are kept separately.',
                              );
                              if (!confirmed) return;

                              await account.clearHistory();
                              _items = [];
                              _hasMore = false;
                              _notice = 'Your analysis history was cleared.';
                            }),
                    icon: const Icon(Icons.delete_sweep_outlined),
                    label: const Text('Clear my history'),
                  ),
                const Divider(height: 40),
                TextButton.icon(
                  key: const ValueKey('delete-account-button'),
                  style: TextButton.styleFrom(
                    foregroundColor: Theme.of(context).colorScheme.error,
                  ),
                  onPressed: _busy ? null : _deleteAccount,
                  icon: const Icon(Icons.person_remove_outlined),
                  label: const Text('Delete my account'),
                ),
              ],
            ],
          ],
        ),
      ),
    );
  }
}

/// Asks for the password before permanently deleting the account.
/// Returns the entered password, or null when cancelled.
class _DeleteAccountDialog extends StatefulWidget {
  const _DeleteAccountDialog();

  @override
  State<_DeleteAccountDialog> createState() => _DeleteAccountDialogState();
}

class _DeleteAccountDialogState extends State<_DeleteAccountDialog> {
  final _passwordController = TextEditingController();

  @override
  void dispose() {
    _passwordController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final canSubmit = _passwordController.text.isNotEmpty;

    return AlertDialog(
      key: const ValueKey('delete-account-dialog'),
      title: const Text('Delete your account?'),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'This permanently deletes your account, signs you out '
              'everywhere, and deletes all your saved analyses. '
              'This cannot be undone.',
            ),
            const SizedBox(height: 12),
            const Text(
              'Message reports you submitted are not linked to your '
              'account and are kept for review.',
            ),
            const SizedBox(height: 16),
            TextField(
              key: const ValueKey('delete-account-password'),
              controller: _passwordController,
              obscureText: true,
              autocorrect: false,
              enableSuggestions: false,
              maxLength: 128,
              onChanged: (_) => setState(() {}),
              decoration: const InputDecoration(
                labelText: 'Enter your password to confirm',
                border: OutlineInputBorder(),
              ),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Cancel'),
        ),
        FilledButton(
          key: const ValueKey('confirm-delete-account-button'),
          style: FilledButton.styleFrom(
            backgroundColor: scheme.error,
            foregroundColor: scheme.onError,
          ),
          onPressed: canSubmit
              ? () => Navigator.pop(context, _passwordController.text)
              : null,
          child: const Text('Delete account'),
        ),
      ],
    );
  }
}
