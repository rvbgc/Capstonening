import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:smishguard/main.dart';

/// Makes the test screen tall enough that nothing needs scrolling.
void useTallScreen(WidgetTester tester) {
  tester.view.physicalSize = const Size(1080, 4000);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
}

/// Answers the automatic server check made when the screen opens.
http.Response? healthResponse(http.Request request) {
  if (request.url.path != '/health') return null;

  return http.Response(
    jsonEncode({'status': 'ok', 'model_ready': true}),
    200,
    headers: {'content-type': 'application/json'},
  );
}

Future<void> tapAnalyzeButton(WidgetTester tester) async {
  final button = find.byKey(const ValueKey('analyze-message-button'));

  await tester.ensureVisible(button);
  await tester.pumpAndSettle();
  expect(button, findsOneWidget);

  await tester.tap(button);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('Empty message is rejected without a request', (tester) async {
    useTallScreen(tester);
    var requests = 0;

    final client = MockClient((request) async {
      final health = healthResponse(request);
      if (health != null) return health;

      requests++;
      return http.Response('{}', 500);
    });
    addTearDown(client.close);

    await tester.pumpWidget(SmishGuardApp(client: client));
    await tapAnalyzeButton(tester);

    expect(find.text('Enter a message first.'), findsOneWidget);
    expect(requests, 0);
  });

  testWidgets('Submitted message displays the unavailable-model response',
      (tester) async {
    useTallScreen(tester);
    var requests = 0;

    final client = MockClient((request) async {
      final health = healthResponse(request);
      if (health != null) return health;

      requests++;

      expect(request.method, 'POST');
      expect(request.url.path, '/analyze');
      expect(jsonDecode(request.body), {'text': 'This is a sample message.'});

      return http.Response(
        jsonEncode({
          'detail': {'code': 'MODEL_NOT_READY'},
        }),
        503,
        headers: {'content-type': 'application/json'},
      );
    });
    addTearDown(client.close);

    await tester.pumpWidget(SmishGuardApp(client: client));
    await tester.enterText(find.byType(TextField), 'This is a sample message.');
    await tapAnalyzeButton(tester);

    expect(requests, 1);
    expect(find.byKey(const ValueKey('status-card')), findsOneWidget);
    expect(
      find.text(
        'The server received your message. '
        'Detection is not available yet. '
        'No risk assessment was made.',
      ),
      findsOneWidget,
    );
    expect(find.byKey(const ValueKey('sms-assessment-card')), findsNothing);
  });

  testWidgets('Successful analysis shows separate SMS and URL cards',
      (tester) async {
    useTallScreen(tester);

    final client = MockClient((request) async {
      final health = healthResponse(request);
      if (health != null) return health;

      expect(request.url.path, '/analyze');

      return http.Response(
        jsonEncode({
          'label': 'smishing',
          'message': 'This message shows common smishing signs.',
          'threat_intelligence': {
            'source': 'PhishHunt',
            'status': 'not_listed',
            'message': 'No cached match was found. '
                'This does not prove the link is safe.',
          },
        }),
        200,
        headers: {'content-type': 'application/json'},
      );
    });
    addTearDown(client.close);

    await tester.pumpWidget(SmishGuardApp(client: client));
    await tester.enterText(find.byType(TextField), 'This is a sample message.');
    await tapAnalyzeButton(tester);

    // SMS assessment card
    expect(find.byKey(const ValueKey('sms-assessment-card')), findsOneWidget);
    expect(find.text('Possible smishing detected'), findsOneWidget);
    expect(
      find.text('This message shows common smishing signs.'),
      findsOneWidget,
    );

    // URL check card
    expect(find.byKey(const ValueKey('url-check-card')), findsOneWidget);
    expect(find.text('No URL match in the PhishHunt feed'), findsOneWidget);
    expect(
      find.text(
        'No cached match was found. This does not prove the link is safe.',
      ),
      findsOneWidget,
    );

    // No error card alongside a successful result
    expect(find.byKey(const ValueKey('status-card')), findsNothing);
  });

  testWidgets('Server connection is checked automatically on open',
      (tester) async {
    useTallScreen(tester);
    var healthChecks = 0;

    final client = MockClient((request) async {
      if (request.url.path == '/health') healthChecks++;
      return healthResponse(request) ?? http.Response('{}', 500);
    });
    addTearDown(client.close);

    await tester.pumpWidget(SmishGuardApp(client: client));
    await tester.pumpAndSettle();

    expect(healthChecks, 1);
    expect(find.text('Server connected. Model is available.'), findsOneWidget);
  });

  testWidgets('Unreachable server shows the address being used',
      (tester) async {
    useTallScreen(tester);

    final client = MockClient((request) async {
      throw http.ClientException('Connection refused', request.url);
    });
    addTearDown(client.close);

    await tester.pumpWidget(SmishGuardApp(client: client));
    await tester.pumpAndSettle();

    expect(
      find.textContaining('Cannot reach the server at http://10.0.2.2:8000'),
      findsOneWidget,
    );
  });
}
