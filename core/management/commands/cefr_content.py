"""Original Multilevel (CEFR) practice material: two mocks per section.

Question types follow the exam's formats. Listening scripts are turned into
audio by `seed_cefr` with the system text-to-speech engine.
"""

# --------------------------------------------------------------------- READING
READING = [
    {
        "title": "Multilevel Reading — Mock 01",
        "level": "B2",
        "time_limit": 30,
        "instructions": "Read the three texts and answer questions 1–14.",
        "parts": [
            {
                "title": "Part 1 · Gap filling",
                "summary": "Community gardens",
                "instructions": "Complete the text. Write ONE word for each gap (1–5).",
                "passage": (
                    "COMMUNITY GARDENS\n\n"
                    "In many cities, empty plots of land are being turned into community gardens. Local residents "
                    "share the work of planting, watering and (1) ______ the vegetables they grow. Most gardens "
                    "are run by volunteers, and anyone who lives in the (2) ______ can join.\n\n"
                    "Supporters say the gardens do much more than produce food. They give people a reason to spend "
                    "time outdoors and help neighbours who have never spoken to each other to become (3) ______. "
                    "Some gardens also offer free classes, so children can learn where their food (4) ______ from.\n\n"
                    "However, the gardens face problems too. Land in city centres is expensive, and owners sometimes "
                    "decide to sell it to builders. For this (5) ______, many groups now ask the city council to "
                    "protect their gardens by law."
                ),
                "questions": [
                    ("gap_filling", "Gap 1", "harvesting|picking|collecting"),
                    ("gap_filling", "Gap 2", "area|neighbourhood|neighborhood|district"),
                    ("gap_filling", "Gap 3", "friends"),
                    ("gap_filling", "Gap 4", "comes"),
                    ("gap_filling", "Gap 5", "reason"),
                ],
            },
            {
                "title": "Part 2 · Matching",
                "summary": "Choosing a course",
                "instructions": "Four people want to take a course. Read the course adverts A–F and choose the "
                                "best course for each person (6–9). There are two extra adverts.",
                "passage": (
                    "A  WEEKEND PHOTOGRAPHY — Two full Saturdays in the city centre. Bring your own camera; "
                    "beginners welcome.\n\n"
                    "B  CODING FOR TEENS — Evening classes for 14–18-year-olds. Build a simple game in eight weeks.\n\n"
                    "C  BUSINESS ENGLISH ONLINE — Live lessons at lunchtime. Practise emails, meetings and "
                    "presentations.\n\n"
                    "D  FAMILY COOKING — Parents and children cook together every Sunday morning. All ingredients "
                    "provided.\n\n"
                    "E  FIRST AID CERTIFICATE — One-day course with an official certificate, required by many "
                    "employers.\n\n"
                    "F  CREATIVE WRITING — Weekly evening workshop for adults. Share your stories and get feedback."
                ),
                "questions": [
                    ("matching", "Aziz works in an office and wants to feel more confident when he speaks to "
                                 "international clients, but he can only study during his lunch break.", "C"),
                    ("matching", "Malika is applying for a job at a summer camp, and the employer has asked "
                                 "all candidates to show proof that they can help injured people.", "E"),
                    ("matching", "Rustam's 15-year-old son spends hours playing video games and would like to "
                                 "learn how they are made.", "B"),
                    ("matching", "Dilnoza has written short stories for years but has never shown them to "
                                 "anyone. She would like honest opinions from other writers.", "F"),
                ],
                "options": [("A", "Weekend Photography"), ("B", "Coding for Teens"), ("C", "Business English Online"),
                            ("D", "Family Cooking"), ("E", "First Aid Certificate"), ("F", "Creative Writing")],
            },
            {
                "title": "Part 3 · True / False / No Information",
                "summary": "Sleep and memory",
                "instructions": "Read the text. Do statements 10–14 agree with the information in the text?",
                "passage": (
                    "SLEEP AND MEMORY\n\n"
                    "For a long time, scientists believed that the brain simply rested during sleep. Research over "
                    "the past thirty years has shown that this is not the case. While we sleep, the brain replays "
                    "information from the day and moves important memories into long-term storage.\n\n"
                    "In one well-known experiment, two groups of students learned a list of words in the evening. "
                    "The first group slept normally, while the second group stayed awake all night. The next "
                    "morning, the students who had slept remembered almost 40 per cent more words.\n\n"
                    "Short naps can also help. A sleep of twenty minutes in the afternoon appears to improve "
                    "attention, although longer naps may leave people feeling tired and confused for a while "
                    "after they wake up. Researchers therefore recommend that students revise in the evening and "
                    "get a full night's sleep before an exam, rather than studying through the night."
                ),
                "questions": [
                    ("true_false_not_given", "Scientists have always known that the brain is active during "
                                             "sleep.", "FALSE"),
                    ("true_false_not_given", "In the experiment, the students learned the words in the "
                                             "evening.", "TRUE"),
                    ("true_false_not_given", "The students who stayed awake were paid to take part.",
                     "NO INFORMATION"),
                    ("true_false_not_given", "Naps longer than twenty minutes can make people feel "
                                             "confused for a short time.", "TRUE"),
                    ("true_false_not_given", "The researchers advise students to study all night before an "
                                             "exam.", "FALSE"),
                ],
            },
        ],
    },
    {
        "title": "Multilevel Reading — Mock 02",
        "level": "B2",
        "time_limit": 30,
        "instructions": "Read the three texts and answer questions 1–13.",
        "parts": [
            {
                "title": "Part 1 · Gap filling",
                "summary": "The modern library",
                "instructions": "Complete the text. Write ONE word for each gap (1–5).",
                "passage": (
                    "THE MODERN LIBRARY\n\n"
                    "Many people think libraries are only places to borrow books, but modern libraries offer much "
                    "(1) ______. Visitors can use computers, print documents and join free workshops on topics "
                    "such as job applications and online safety.\n\n"
                    "Libraries are also among the few public places where people can stay for hours without "
                    "having to (2) ______ any money. Students come to study in silence, while parents bring young "
                    "children to story sessions at the weekend.\n\n"
                    "Because fewer people borrow printed books than in the past, some libraries have had to "
                    "(3) ______ their opening hours. Others have found new ways to attract visitors, for example "
                    "by lending tools, musical instruments and even (4) ______ games. Librarians say the most "
                    "important thing is to listen to what the local community (5) ______."
                ),
                "questions": [
                    ("gap_filling", "Gap 1", "more"),
                    ("gap_filling", "Gap 2", "spend|pay"),
                    ("gap_filling", "Gap 3", "reduce|cut|shorten"),
                    ("gap_filling", "Gap 4", "board|video|computer"),
                    ("gap_filling", "Gap 5", "needs|wants"),
                ],
            },
            {
                "title": "Part 2 · Headings",
                "summary": "Learning a language as an adult",
                "instructions": "Choose the correct heading for paragraphs A–D (6–9) from the list i–vi. "
                                "There are two extra headings.",
                "passage": (
                    "LEARNING A LANGUAGE AS AN ADULT\n\n"
                    "A  Children seem to pick up languages without effort, and many adults believe they are simply "
                    "too old to learn. Research does not support this view: adults often make faster progress than "
                    "children in the first months, because they can use what they know about grammar and "
                    "learning.\n\n"
                    "B  Where adults usually struggle is pronunciation. After the age of about twelve, it becomes "
                    "harder to hear and produce sounds that do not exist in your first language, so most adult "
                    "learners keep some accent.\n\n"
                    "C  The biggest difference, however, is time. A child at school may hear a new language for "
                    "several hours every day, while a busy adult can often manage only an hour or two a week. "
                    "Experts say that short daily practice is more effective than one long weekly lesson.\n\n"
                    "D  Finally, motivation matters more than age. Adults who learn a language for a clear reason "
                    "— a new job, a move abroad or a partner's family — are far more likely to continue than "
                    "those who start just because they think they should."
                ),
                "questions": [
                    ("headings", "Paragraph A", "ii"),
                    ("headings", "Paragraph B", "v"),
                    ("headings", "Paragraph C", "i"),
                    ("headings", "Paragraph D", "iv"),
                ],
                "options": [("i", "Little and often"), ("ii", "A common belief is wrong"),
                            ("iii", "Why children forget languages"), ("iv", "Having a goal"),
                            ("v", "The hardest skill for adults"), ("vi", "The best age to start")],
            },
            {
                "title": "Part 3 · Multiple choice",
                "summary": "Shared e-scooters",
                "instructions": "Read the text and choose the correct answer A, B, C or D (10–13).",
                "passage": (
                    "SHARED E-SCOOTERS\n\n"
                    "Five years ago, electric scooters that anyone could rent with a phone app appeared in cities "
                    "around the world. Companies promised that they would reduce traffic, because people would "
                    "use them instead of cars for short journeys.\n\n"
                    "Studies have since shown a more complicated picture. In several cities, most scooter trips "
                    "replaced walking or public transport rather than car journeys, so the effect on traffic was "
                    "small. The scooters themselves also caused problems: they were often left lying on "
                    "pavements, where they blocked the way for people with prams or wheelchairs.\n\n"
                    "Many cities responded with new rules. Riders must now park in marked areas, and in some "
                    "places scooters slow down automatically in busy streets. Paris went further and banned "
                    "rental scooters completely after residents voted against them. Supporters argue that, with "
                    "the right rules, scooters can still play a useful role, especially in areas where buses are "
                    "rare."
                ),
                "mcq": [
                    ("What did scooter companies originally claim?",
                     [("A", "Scooters would be cheaper than buses.", False),
                      ("B", "Scooters would replace short car trips.", True),
                      ("C", "Scooters would be popular with tourists.", False),
                      ("D", "Scooters would be safer than bicycles.", False)]),
                    ("According to studies, most scooter trips replaced",
                     [("A", "car journeys.", False), ("B", "bicycle rides.", False),
                      ("C", "taxi journeys.", False), ("D", "walking or public transport.", True)]),
                    ("Why were scooters a problem for people with wheelchairs?",
                     [("A", "They were left on pavements.", True), ("B", "They were too fast.", False),
                      ("C", "They were too expensive to rent.", False),
                      ("D", "They could not be used on roads.", False)]),
                    ("What happened in Paris?",
                     [("A", "Scooters were limited to some streets.", False),
                      ("B", "Riders had to buy a licence.", False),
                      ("C", "Rental scooters were banned after a vote.", True),
                      ("D", "Scooters were only allowed near bus stops.", False)]),
                ],
            },
        ],
    },
]

# ------------------------------------------------------------------- LISTENING
# Each part: script = list of (voice, text). Voices are macOS `say` voices.
LISTENING = [
    {
        "title": "Multilevel Listening — Mock 01",
        "level": "B1",
        "time_limit": 25,
        "instructions": "You will hear four parts. Answer questions 1–16.",
        "parts": [
            {
                "title": "Part 1 · Short conversations",
                "summary": "Short conversations (A/B/C)",
                "instructions": "You will hear four short conversations. Choose the correct answer A, B or C (1–4).",
                "script": [
                    ("Daniel", "Part one. Question one. Where are the speakers going to meet?"),
                    ("Samantha", "Shall we meet at the café before the film?"),
                    ("Daniel", "The café will be too busy on a Friday. Let's just meet outside the cinema at "
                               "seven."),
                    ("Samantha", "Fine. Outside the cinema, then."),
                    ("Daniel", "Question two. What time does the train leave?"),
                    ("Karen", "Excuse me, is the train to Samarkand still at ten fifteen?"),
                    ("Daniel", "It was, but there's a delay this morning. It's leaving at ten forty-five now."),
                    ("Daniel", "Question three. What does the woman want to buy?"),
                    ("Moira", "I'm looking for a present for my brother. I was thinking of a book, but he "
                              "reads everything online these days."),
                    ("Daniel", "What about headphones? These are very popular."),
                    ("Moira", "Oh, that's a good idea. He's always listening to music. I'll take them."),
                    ("Daniel", "Question four. Why is the man late?"),
                    ("Samantha", "You're late again! What happened this time?"),
                    ("Daniel", "Sorry. The bus was on time, but I left my keys at home and had to go back for "
                               "them."),
                ],
                "mcq": [
                    ("Where are the speakers going to meet?",
                     [("A", "at a café", False), ("B", "outside the cinema", True), ("C", "at the bus stop", False)]),
                    ("What time does the train leave?",
                     [("A", "10:15", False), ("B", "10:30", False), ("C", "10:45", True)]),
                    ("What does the woman buy for her brother?",
                     [("A", "a book", False), ("B", "headphones", True), ("C", "a music album", False)]),
                    ("Why is the man late?",
                     [("A", "He forgot his keys.", True), ("B", "The bus was late.", False),
                      ("C", "He overslept.", False)]),
                ],
            },
            {
                "title": "Part 2 · Note completion",
                "summary": "City History Museum tour",
                "instructions": "You will hear an announcement about a museum tour. Complete the notes. "
                                "Write ONE word or a NUMBER for each answer (5–8).",
                "script": [
                    ("Daniel", "Part two. Listen to the announcement and complete the notes."),
                    ("Tessa", "Good morning and welcome to the City History Museum. Our guided tour starts in "
                              "ten minutes from the main entrance hall. The tour lasts about ninety minutes, and "
                              "it costs twenty thousand sum per person. Students with a valid card pay half "
                              "price. Please leave large bags in the cloakroom on the ground floor, as they are "
                              "not allowed in the galleries. Photography is permitted, but please do not use a "
                              "flash. At the end of the tour, you are welcome to visit our café on the top "
                              "floor, which has a wonderful view of the old city. Thank you, and enjoy your "
                              "visit."),
                ],
                "notes": [
                    ("The tour lasts about ______ minutes.", "90|ninety"),
                    ("Students with a card pay ______ price.", "half"),
                    ("Large bags must be left in the ______.", "cloakroom"),
                    ("Visitors may take photos but must not use a ______.", "flash"),
                ],
            },
            {
                "title": "Part 3 · Conversation",
                "summary": "A geography project",
                "instructions": "You will hear two students talking about a project. Choose the correct answer "
                                "A, B or C (9–11).",
                "script": [
                    ("Daniel", "Part three. Listen to two students discussing a project."),
                    ("Samantha", "Have you decided on a topic for our geography project yet?"),
                    ("Daniel", "I was thinking about water. Maybe how much water families in our city use "
                               "every day."),
                    ("Samantha", "That's interesting, but it might be hard to get real numbers. What if we "
                                 "made a short survey and asked students in our school instead?"),
                    ("Daniel", "Good idea. We could ask about showers, washing clothes and so on. How many "
                               "people should we ask?"),
                    ("Samantha", "The teacher said at least thirty, but let's try for fifty to be safe."),
                    ("Daniel", "OK. And I think a short video would be better than a poster for the "
                               "presentation. People remember videos."),
                    ("Samantha", "I agree. I can do the filming if you write the questions."),
                ],
                "mcq": [
                    ("What is the topic of the project?",
                     [("A", "air pollution", False), ("B", "water use", True), ("C", "school transport", False)]),
                    ("How many people do they plan to ask?",
                     [("A", "30", False), ("B", "40", False), ("C", "50", True)]),
                    ("How will they present their results?",
                     [("A", "with a video", True), ("B", "with a poster", False), ("C", "with a report", False)]),
                ],
            },
            {
                "title": "Part 4 · Label the map",
                "summary": "Town centre changes",
                "instructions": "You will hear a town planner talking about changes to the town centre. "
                                "Label the map. Choose the correct letter A–H for each place (12–16).",
                "map": True,
                "script": [
                    ("Daniel", "Part four. Look at the map and listen to a town planner."),
                    ("Moira", "Good evening, everyone. I'd like to show you the changes we are planning for the "
                              "town centre. Please look at the map. First, the new traffic lights. These will be "
                              "at the junction where Park Road meets High Street, because that is where most "
                              "accidents happen. Next, we are adding a pedestrian crossing on High Street, right "
                              "outside the library, so that schoolchildren can cross safely. Near the station, "
                              "at the western end of High Street, we are putting in bicycle parking for about "
                              "fifty bikes. The bus stop is also moving. It will be on the south side of High "
                              "Street, directly in front of the bank. And finally, some good news: a new café "
                              "will open at the top of Park Road, next to the entrance to the park."),
                ],
                "questions": [
                    ("map_labelling", "New traffic lights", "D"),
                    ("map_labelling", "Pedestrian crossing", "C"),
                    ("map_labelling", "Bicycle parking", "B"),
                    ("map_labelling", "Bus stop", "E"),
                    ("map_labelling", "New café", "A"),
                ],
                "options": [(letter, "") for letter in "ABCDEFGH"],
            },
        ],
    },
    {
        "title": "Multilevel Listening — Mock 02",
        "level": "B1",
        "time_limit": 25,
        "instructions": "You will hear three parts. Answer questions 1–11.",
        "parts": [
            {
                "title": "Part 1 · Short conversations",
                "summary": "Short conversations (A/B/C)",
                "instructions": "You will hear four short conversations. Choose the correct answer A, B or C (1–4).",
                "script": [
                    ("Daniel", "Part one. Question one. How will the woman travel to work tomorrow?"),
                    ("Karen", "My car is at the garage until Thursday, so I'll have to take the metro "
                              "tomorrow."),
                    ("Daniel", "Why not cycle? It's only twenty minutes."),
                    ("Karen", "In this rain? No, thanks. The metro it is."),
                    ("Daniel", "Question two. What is the weather going to be like at the weekend?"),
                    ("Moira", "It's been so cold this week. Is it going to get any warmer?"),
                    ("Daniel", "The forecast says Saturday and Sunday will be sunny, but still quite cold, "
                               "especially in the evenings."),
                    ("Daniel", "Question three. Which room is the meeting in?"),
                    ("Samantha", "Is the meeting still in room twelve?"),
                    ("Daniel", "No, room twelve is being painted. We've moved to room twenty, on the second "
                               "floor."),
                    ("Daniel", "Question four. What does the man order?"),
                    ("Tessa", "What would you like?"),
                    ("Daniel", "I'll have the chicken soup, please. Actually, no, I'm really hungry. I'll have "
                               "the rice with vegetables instead."),
                ],
                "mcq": [
                    ("How will the woman travel to work tomorrow?",
                     [("A", "by car", False), ("B", "by bicycle", False), ("C", "by metro", True)]),
                    ("What will the weather be like at the weekend?",
                     [("A", "sunny and cold", True), ("B", "rainy and warm", False), ("C", "cloudy and windy", False)]),
                    ("Which room is the meeting in?",
                     [("A", "room 12", False), ("B", "room 20", True), ("C", "room 2", False)]),
                    ("What does the man order?",
                     [("A", "chicken soup", False), ("B", "rice with vegetables", True), ("C", "a salad", False)]),
                ],
            },
            {
                "title": "Part 2 · Note completion",
                "summary": "Green Park Sports Centre",
                "instructions": "You will hear information about a sports centre. Complete the notes. "
                                "Write ONE word or a NUMBER for each answer (5–8).",
                "script": [
                    ("Daniel", "Part two. Listen to the information and complete the notes."),
                    ("Moira", "Thank you for calling the Green Park Sports Centre. We are open from six in the "
                              "morning until ten at night, every day except Sunday, when we close at eight. "
                              "Monthly membership costs one hundred and fifty thousand sum and includes the gym "
                              "and the swimming pool. Tennis courts must be booked separately, at least one day "
                              "in advance. New members get a free fitness check with one of our trainers. To "
                              "join, please bring a photo and your passport to reception."),
                ],
                "notes": [
                    ("On Sunday the centre closes at ______ pm.", "8|eight"),
                    ("Membership includes the gym and the swimming ______.", "pool"),
                    ("Tennis courts must be booked one ______ in advance.", "day"),
                    ("To join, bring a photo and your ______.", "passport"),
                ],
            },
            {
                "title": "Part 3 · Interview",
                "summary": "Volunteering at an animal shelter",
                "instructions": "You will hear an interview with a volunteer. Choose the correct answer A, B or C "
                                "(9–11).",
                "script": [
                    ("Daniel", "Part three. Listen to an interview with a volunteer."),
                    ("Samantha", "Today I'm talking to Daniel, who volunteers at an animal shelter. How did you "
                                 "start?"),
                    ("Daniel", "My neighbour worked there, and one weekend she needed extra help. I went along, "
                               "and I've been going every Saturday since then. That was three years ago."),
                    ("Samantha", "What do you do there?"),
                    ("Daniel", "Mostly I walk the dogs and clean the cages. It isn't glamorous, but the animals "
                               "really need the exercise."),
                    ("Samantha", "What's the hardest part?"),
                    ("Daniel", "Saying goodbye, actually. When a dog finds a new home, I'm happy, of course, "
                               "but I always miss it a little."),
                ],
                "mcq": [
                    ("How did Daniel start volunteering?",
                     [("A", "He saw an advert online.", False), ("B", "His neighbour asked for help.", True),
                      ("C", "His school organised it.", False)]),
                    ("How long has he been volunteering?",
                     [("A", "one year", False), ("B", "two years", False), ("C", "three years", True)]),
                    ("What does he find most difficult?",
                     [("A", "cleaning the cages", False), ("B", "saying goodbye to the animals", True),
                      ("C", "walking big dogs", False)]),
                ],
            },
        ],
    },
]

# --------------------------------------------------------------------- WRITING
WRITING = [
    {
        "title": "Multilevel Writing — Mock 01",
        "summary": "Cooking club changes",
        "task_summaries": ["informal message · to a friend", "formal letter · to the club manager",
                           "Should schools teach cooking?"],
        "level": "B2",
        "time_limit": 60,
        "instructions": "Complete all three tasks in 60 minutes.",
        "situation": "You are a member of a cooking club. The club manager has announced that, from next month, "
                     "meetings will move from Wednesday evenings to Saturday mornings, and the monthly fee will "
                     "increase.",
        "tasks": [
            ("task1_1", "Task 1.1", 50, 70, 15,
             "Write a short message to your friend, who is also a club member. Tell them about the change, say how "
             "you feel about it and suggest what you could do together."),
            ("task1_2", "Task 1.2", 120, 150, 20,
             "Write a letter to the club manager. Explain how the changes affect you, give your opinion and "
             "suggest a solution."),
            ("task2", "Task 2", 180, 200, 25,
             "Some people think that young people should learn to cook at school, while others believe this is "
             "the responsibility of parents. Discuss both views and give your own opinion."),
        ],
    },
    {
        "title": "Multilevel Writing — Mock 02",
        "summary": "Library weekend closure",
        "task_summaries": ["informal message · to a study friend", "formal letter · to the library director",
                           "Screens vs printed books"],
        "level": "B2",
        "time_limit": 60,
        "instructions": "Complete all three tasks in 60 minutes.",
        "situation": "Your city's public library has announced that it will close its reading room on weekends "
                     "to save money. The reading room will remain open on weekdays from 9 am to 5 pm.",
        "tasks": [
            ("task1_1", "Task 1.1", 50, 70, 15,
             "Write a short message to a friend who often studies with you in the library. Tell them the news and "
             "suggest another place to study."),
            ("task1_2", "Task 1.2", 120, 150, 20,
             "Write a letter to the library director. Explain why the weekend closure is a problem for students "
             "like you and suggest how the library could save money in another way."),
            ("task2", "Task 2", 180, 200, 25,
             "Nowadays many people prefer to read on screens rather than read printed books. What are the "
             "advantages and disadvantages of this trend? Give reasons and examples."),
        ],
    },
]

# -------------------------------------------------------------------- SPEAKING
# (part, question, cue/argument lines, prep, speak)
SPEAKING = [
    {
        "title": "Multilevel Speaking — Mock 01",
        "summaries": {1: "Free time & your city", 2: "Train vs plane travel", 3: "A person who helped you",
                      4: "Social media and young people"},
        "level": "B2",
        "time_limit": 20,
        "questions": [
            (1, "What do you usually do in your free time?", "", 5, 30),
            (1, "Do you prefer spending time at home or going out? Why?", "", 5, 30),
            (1, "Tell me about a place in your city that you like.", "", 5, 30),
            (2, "Compare these two ways of travelling: travelling by train and travelling by plane. Talk about "
                "what is good and bad about each.", "", 10, 45),
            (2, "Which way of travelling would you choose for a long holiday? Why?", "", 5, 30),
            (2, "Do you think people travel too much nowadays?", "", 5, 30),
            (3, "Describe a person who has helped you in your life.",
             "who the person is\nhow you know them\nwhat they did to help you\nand explain how you feel about them",
             60, 120),
            (4, "Social media does more harm than good for young people.",
             "For: It wastes a lot of time\nFor: It can damage self-confidence\n"
             "Against: It helps people stay in touch\nAgainst: It is a quick way to learn new things",
             60, 120),
        ],
    },
    {
        "title": "Multilevel Speaking — Mock 02",
        "summaries": {1: "Study, music & transport", 2: "Studying alone vs in a group", 3: "A skill to learn",
                      4: "Compulsory volunteer work"},
        "level": "B2",
        "time_limit": 20,
        "questions": [
            (1, "Do you work or are you a student?", "", 5, 30),
            (1, "What kind of music do you enjoy?", "", 5, 30),
            (1, "How often do you use public transport?", "", 5, 30),
            (2, "Compare studying alone at home and studying in a group at a library. Talk about the advantages "
                "and disadvantages of each.", "", 10, 45),
            (2, "Which do you find more effective for learning English? Why?", "", 5, 30),
            (2, "Should schools give students more group projects?", "", 5, 30),
            (3, "Describe a skill you would like to learn in the future.",
             "what the skill is\nwhy you want to learn it\nhow you will learn it\nand explain how it could change "
             "your life", 60, 120),
            (4, "Everyone should do some kind of volunteer work.",
             "For: It helps the community\nFor: It teaches useful skills\n"
             "Against: Many people are too busy\nAgainst: Work should always be paid",
             60, 120),
        ],
    },
]
