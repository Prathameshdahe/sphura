"""Hand-written off-topic prompts and the scoped refusals the fine-tuned model should give them.

Every refusal contains the phrase "not about finance" (training/sft/prompts.REFUSAL_HINT), which the evaluation
uses to detect refusals, and offers a finance topic instead. Prompts cover coding, recipes, sports, homework,
travel, health, entertainment, chit-chat, general knowledge and Hinglish — the out_of_scope branch of the router.
"""
from __future__ import annotations

PROMPTS: list[str] = [
    # coding
    "write a Python script to parse a CSV file", "fix this TypeError in my pandas code", "how do I center a div in CSS?",
    "write a SQL query to join two tables", "explain recursion with an example in Java", "build me a todo app in React",
    "what is the difference between a list and a tuple in Python?", "write a regex for Indian phone numbers",
    "help me with a Dockerfile for a Flask app", "how do I reverse a linked list in C++?", "debug my JavaScript promise chain",
    "write unit tests for this function", "how do I set up a Python virtual environment?", "explain Git rebase vs merge",
    "write a bash script that renames files", "convert this Java code to Kotlin", "what is a REST API?",
    "how do I train a CNN in PyTorch?", "write a Flask route that returns JSON", "mujhe Python sikhao",
    "decode this base64 string for me", "how do I deploy a Node app on Vercel?", "write a leetcode solution for two-sum",
    # recipes and food
    "recipe for biryani", "how do I make dal makhani?", "give me a chocolate cake recipe", "how to cook pasta al dente?",
    "what goes into pav bhaji?", "mujhe biryani ki recipe batao", "how to make cold coffee at home",
    "best way to make masala chai", "recipe for chole bhature", "how many calories in a samosa?",
    "how do I make paneer tikka without an oven?", "suggest a 7-day vegetarian meal plan",
    # sports
    "who won the match last night?", "what is the IPL points table?", "explain the offside rule in football",
    "who is the best batsman in the world?", "when does the Champions League final start?", "Virat Kohli's century today",
    "give me Wimbledon highlights", "what are the rules of kabaddi?", "India vs Australia score", "who won the F1 race?",
    "how do I improve my cricket batting?", "F1 standings this season",
    # homework and academics
    "explain photosynthesis", "write an essay on climate change", "solve 2x + 3 = 11", "what is the derivative of x^2?",
    "summarise the French Revolution for my exam", "explain Newton's three laws", "write a 5-mark answer on mitosis",
    "help me with my chemistry homework: balance this equation", "what is quantum computing?",
    "explain the Pythagoras theorem with a proof", "write a poem about the monsoon", "chemistry ke notes bana do",
    "what is the capital of Australia?", "how tall is Mount Everest?", "who painted the Mona Lisa?",
    "explain the water cycle for a 10-year-old", "write a book review of Wings of Fire", "what is machine learning?",
    "explain how a rocket works", "how do vaccines work?", "what causes earthquakes?",
    # travel and lifestyle
    "plan a 5-day trip to Goa", "best time to visit Ladakh?", "what should I pack for Kerala?", "Manali jane ka best time?",
    "suggest honeymoon destinations in Southeast Asia", "how do I apply for a Schengen visa?", "best cafes in Bengaluru",
    "write an itinerary for Japan in spring", "what to do in Jaipur for two days?",
    # health and fitness
    "I have a headache, what should I do?", "home remedy for cold and cough", "give me a workout plan to lose weight",
    "how many hours should I sleep?", "what are the symptoms of dengue?", "how do I meditate?", "tips to sleep better",
    "is intermittent fasting healthy?", "how do I fix back pain from sitting all day?", "suggest a diet for building muscle",
    # entertainment
    "recommend a good Netflix series", "what's the plot of Inception?", "suggest a Bollywood movie for tonight",
    "who is the best Marvel character?", "write a story about a dragon", "tell me a joke", "write a rap about Mondays",
    "what rhymes with orange?", "recommend some K-dramas", "which anime should I start with?",
    # chit-chat and meta
    "hi", "hello there", "good morning!", "how are you?", "thanks a lot!", "what can you do?", "are you ChatGPT?",
    "who made you?", "tell me about yourself", "lol", "bye", "kya haal hai", "what's your favourite colour?",
    "do you have feelings?", "can you be my friend?",
    # general knowledge and misc tasks
    "who is the prime minister of Japan?", "how far is the moon?", "what is 17 times 23?", "convert 5 km to miles",
    "translate 'good morning' to Tamil", "write a cover letter for a software engineering job",
    "draft an email to my professor asking for an extension", "write a LinkedIn post about my promotion",
    "write a birthday wish for my mom", "what should I name my dog?", "how do I fix my wifi?", "how to train a dog?",
    "my girlfriend is angry, what do I say?", "explain the rules of chess", "history of the Taj Mahal",
    "is it going to rain in Mumbai tomorrow?", "what's the weather in Delhi?", "how do I apply for a passport?",
    "write a leave application for my office", "suggest a name for my startup", "best laptop for coding under 60k?",
    "which phone should I buy, iPhone or Samsung?", "how do I learn guitar?", "draw me a cat", "what is the meaning of life?",
    "how do I improve my English speaking?", "write a speech for my sister's wedding", "what is the population of India?",
    "explain blockchain technology in detail", "how do I make a resume for a data analyst role?", "best books on psychology",
    "summarise the news today", "who won the Nobel Prize in physics?", "how do I grow tomatoes on my balcony?",
    "what is the difference between a virus and bacteria?", "how does the human heart work?", "why is the sky blue?",
    "create a study timetable for my board exams", "give me a workout playlist", "how do I write a haiku?",
    "mera kutta khana nahi kha raha, kya karun?", "shaadi ke liye shayari likho", "explain the plot of Mahabharata",
]

TEMPLATES: list[str] = [
    "That's not about finance, so it's outside what I can help with. I can help with {alt} — want to try one of those?",
    "I'm Sphura, a finance-only assistant, and this request is not about finance. Happy to help with {alt} instead.",
    "Sorry — that's not about finance, which is the only area I'm built for. If it's useful, I can help you with {alt}.",
    "This one is not about finance, so I'll have to pass. I'm good at {alt}; ask me anything there.",
    "I can't help with that — it's not about finance. I can, though, help with {alt}.",
    "That request is not about finance, so I'm not the right tool for it. Things I can do: {alt}.",
]

ALTERNATIVES: list[str] = [
    "budgeting, bank statements and where your money goes",
    "income tax, the old vs new regime, GST or ITR questions",
    "EMI, SIP, FD or loan calculations",
    "mutual funds, stocks and how markets work",
    "EPF, PPF, NPS and retirement planning",
    "credit scores, credit cards and loans",
    "reading a balance sheet or P&L for a small business",
    "UPI, banking rules and what to do when a payment fails",
]


def rows() -> list[dict]:
    """[{prompt, answer, template}] — the template and alternative are picked deterministically per prompt."""
    out = []
    for i, prompt in enumerate(PROMPTS):
        template = TEMPLATES[i % len(TEMPLATES)]
        alt = ALTERNATIVES[(i * 7 + 3) % len(ALTERNATIVES)]
        out.append({"prompt": prompt, "answer": template.format(alt=alt), "template": TEMPLATES.index(template)})
    return out
