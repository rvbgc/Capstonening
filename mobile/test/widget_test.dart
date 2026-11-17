import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:smishguard/main.dart';

/// Scrolls the Analyze button into view and taps it.
Future<void> tapAnalyzeButton(WidgetTester tester) async {
  final analyzeButton = find.text('Analyze Message');

  await tester.scrollUntilVisible(
    analyzeButton,
    200,
    scrollable: find.byType(Scrollable).first,
    maxScrolls: 30,
  );

  await tester.pumpAndSettle();
  expect(analyzeButton, findsOneWidget);

  await tester.tap(analyzeButton);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('Empty message is rejected without a request', (tester) async {
    var requests = 0;

    final client = MockClient((request) async {
      requests++;
      return http.Response('{}', 500);
    });

    addTearDown(client.close);

    await tester.pumpWidget(SmishGuardApp(client: client));

    await tapAnalyzeButton(tester);

    expect(find.text('Enter a message first.'), findsOneWidget);
    expect(requests, 0);
  });

  testWidgets('Submitted message displays the unavailable-model response', (
    tester,
  ) async {
    var requests = 0;

    final client = MockClient((request) async {
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
    expect(
      find.text(
        'The server received your message. '
        'Detection is not available yet. '
        'No risk assessment was made.',
      ),
      findsOneWidget,
    );
  });
}
