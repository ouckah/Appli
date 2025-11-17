while True:
  dom = await page.content()
  
  agent_output = llm.chat([
    {"role": "system", "content": PLAYWRIGHT_AGENT_PROMPT},
    {"role": "user", "content": dom},
    {"role": "user", "content": "User profile: " + json.dumps(profile)}
  ])

  action = json.loads(agent_output)

  if action["action"] == "done":
    break

  await execute_playwright_step(action)