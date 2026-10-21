"""Milli takım adlarının Türkçesi (FotMob İngilizce verir). Listede olmayan ad olduğu gibi kalır; eklemek için TR'ye
bir satır yaz. Eleme tablosundaki yer tutucular ('Winner QF 1', '1A', '3ABC') kuralla çevrilir."""
import re

TR = {
    'Afghanistan': 'Afganistan', 'Albania': 'Arnavutluk', 'Algeria': 'Cezayir', 'American Samoa': 'Amerikan Samoası',
    'Andorra': 'Andorra', 'Angola': 'Angola', 'Anguilla': 'Anguilla', 'Antigua and Barbuda': 'Antigua ve Barbuda',
    'Argentina': 'Arjantin', 'Armenia': 'Ermenistan', 'Aruba': 'Aruba', 'Australia': 'Avustralya', 'Austria': 'Avusturya',
    'Azerbaijan': 'Azerbaycan', 'Bahamas': 'Bahamalar', 'Bahrain': 'Bahreyn', 'Bangladesh': 'Bangladeş',
    'Barbados': 'Barbados', 'Belarus': 'Belarus', 'Belgium': 'Belçika', 'Belize': 'Belize', 'Benin': 'Benin',
    'Bermuda': 'Bermuda', 'Bhutan': 'Butan', 'Bolivia': 'Bolivya', 'Bonaire': 'Bonaire',
    'Bosnia and Herzegovina': 'Bosna-Hersek', 'Botswana': 'Botsvana', 'Brazil': 'Brezilya',
    'British Virgin Islands': 'Britanya Virjin Adaları', 'Brunei': 'Brunei', 'Bulgaria': 'Bulgaristan',
    'Burkina Faso': 'Burkina Faso', 'Burundi': 'Burundi', 'Cambodia': 'Kamboçya', 'Cameroon': 'Kamerun',
    'Canada': 'Kanada', 'Cape Verde': 'Yeşil Burun Adaları', 'Cayman Islands': 'Cayman Adaları',
    'Central African Republic': 'Orta Afrika Cumhuriyeti', 'Chad': 'Çad', 'Chile': 'Şili', 'China': 'Çin',
    'Chinese Taipei': 'Çin Taipei', 'Colombia': 'Kolombiya', 'Comoros': 'Komorlar', 'Congo': 'Kongo',
    'Cook Islands': 'Cook Adaları', 'Costa Rica': 'Kosta Rika', 'Croatia': 'Hırvatistan', 'Cuba': 'Küba',
    'Curacao': 'Curaçao', 'Cyprus': 'Güney Kıbrıs', 'Czechia': 'Çekya', 'DR Congo': 'Demokratik Kongo',
    'Denmark': 'Danimarka', 'Djibouti': 'Cibuti', 'Dominica': 'Dominika', 'Dominican Republic': 'Dominik Cumhuriyeti',
    'Ecuador': 'Ekvador', 'Egypt': 'Mısır', 'El Salvador': 'El Salvador', 'England': 'İngiltere',
    'Equatorial Guinea': 'Ekvator Ginesi', 'Eritrea': 'Eritre', 'Estonia': 'Estonya', 'Eswatini': 'Esvatini',
    'Ethiopia': 'Etiyopya', 'Faroe Islands': 'Faroe Adaları', 'Fiji': 'Fiji', 'Finland': 'Finlandiya', 'France': 'Fransa',
    'French Guiana': 'Fransız Guyanası', 'Gabon': 'Gabon', 'Gambia': 'Gambiya', 'Georgia': 'Gürcistan',
    'Germany': 'Almanya', 'Ghana': 'Gana', 'Gibraltar': 'Cebelitarık', 'Greece': 'Yunanistan', 'Grenada': 'Grenada',
    'Guadeloupe': 'Guadeloupe', 'Guam': 'Guam', 'Guatemala': 'Guatemala', 'Guinea': 'Gine', 'Guinea-Bissau': 'Gine-Bissau',
    'Guyana': 'Guyana', 'Haiti': 'Haiti', 'Honduras': 'Honduras', 'Hong Kong': 'Hong Kong', 'Hungary': 'Macaristan',
    'Iceland': 'İzlanda', 'India': 'Hindistan', 'Indonesia': 'Endonezya', 'Iran': 'İran', 'Iraq': 'Irak',
    'Ireland': 'İrlanda', 'Israel': 'İsrail', 'Italy': 'İtalya', 'Ivory Coast': 'Fildişi Sahili', 'Jamaica': 'Jamaika',
    'Japan': 'Japonya', 'Jordan': 'Ürdün', 'Kazakhstan': 'Kazakistan', 'Kenya': 'Kenya', 'Kosovo': 'Kosova',
    'Kuwait': 'Kuveyt', 'Kyrgyzstan': 'Kırgızistan', 'Laos': 'Laos', 'Latvia': 'Letonya', 'Lebanon': 'Lübnan',
    'Lesotho': 'Lesotho', 'Liberia': 'Liberya', 'Libya': 'Libya', 'Liechtenstein': 'Lihtenştayn', 'Lithuania': 'Litvanya',
    'Luxembourg': 'Lüksemburg', 'Macao': 'Makao', 'Madagascar': 'Madagaskar', 'Malawi': 'Malavi', 'Malaysia': 'Malezya',
    'Maldives': 'Maldivler', 'Mali': 'Mali', 'Malta': 'Malta', 'Martinique': 'Martinik', 'Mauritania': 'Moritanya',
    'Mauritius': 'Mauritius', 'Mexico': 'Meksika', 'Moldova': 'Moldova', 'Mongolia': 'Moğolistan',
    'Montenegro': 'Karadağ', 'Montserrat': 'Montserrat', 'Morocco': 'Fas', 'Mozambique': 'Mozambik', 'Myanmar': 'Myanmar',
    'Namibia': 'Namibya', 'Nepal': 'Nepal', 'Netherlands': 'Hollanda', 'New Caledonia': 'Yeni Kaledonya',
    'New Zealand': 'Yeni Zelanda', 'Nicaragua': 'Nikaragua', 'Niger': 'Nijer', 'Nigeria': 'Nijerya',
    'North Korea': 'Kuzey Kore', 'North Macedonia': 'Kuzey Makedonya', 'Northern Ireland': 'Kuzey İrlanda',
    'Norway': 'Norveç', 'Oman': 'Umman', 'Pakistan': 'Pakistan', 'Palestine': 'Filistin', 'Panama': 'Panama',
    'Papua New Guinea': 'Papua Yeni Gine', 'Paraguay': 'Paraguay', 'Peru': 'Peru', 'Philippines': 'Filipinler',
    'Poland': 'Polonya', 'Portugal': 'Portekiz', 'Puerto Rico': 'Porto Riko', 'Qatar': 'Katar', 'Romania': 'Romanya',
    'Russia': 'Rusya', 'Rwanda': 'Ruanda', 'Saint Lucia': 'Saint Lucia', 'Saint Martin': 'Saint Martin',
    'Saint Vincent and The Grenadines': 'Saint Vincent ve Grenadinler', 'Samoa': 'Samoa', 'San Marino': 'San Marino',
    'Sao Tome and Principe': 'São Tomé ve Príncipe', 'Saudi Arabia': 'Suudi Arabistan', 'Scotland': 'İskoçya',
    'Senegal': 'Senegal', 'Serbia': 'Sırbistan', 'Seychelles': 'Seyşeller', 'Sierra Leone': 'Sierra Leone',
    'Singapore': 'Singapur', 'Sint Maarten': 'Sint Maarten', 'Slovakia': 'Slovakya', 'Slovenia': 'Slovenya',
    'Solomon Islands': 'Solomon Adaları', 'Somalia': 'Somali', 'South Africa': 'Güney Afrika', 'South Korea': 'Güney Kore',
    'South Sudan': 'Güney Sudan', 'Spain': 'İspanya', 'Sri Lanka': 'Sri Lanka', 'St. Kitts and Nevis': 'Saint Kitts ve Nevis',
    'Sudan': 'Sudan', 'Suriname': 'Surinam', 'Sweden': 'İsveç', 'Switzerland': 'İsviçre', 'Syria': 'Suriye',
    'Tahiti': 'Tahiti', 'Tajikistan': 'Tacikistan', 'Tanzania': 'Tanzanya', 'Thailand': 'Tayland',
    'Timor-Leste': 'Doğu Timor', 'Togo': 'Togo', 'Tonga': 'Tonga', 'Trinidad and Tobago': 'Trinidad ve Tobago',
    'Tunisia': 'Tunus', 'Turkiye': 'Türkiye', 'Turkey': 'Türkiye', 'Turkmenistan': 'Türkmenistan',
    'Turks and Caicos Islands': 'Turks ve Caicos Adaları', 'U.S. Virgin Islands': 'ABD Virjin Adaları',
    'UAE': 'Birleşik Arap Emirlikleri', 'USA': 'ABD', 'Uganda': 'Uganda', 'Ukraine': 'Ukrayna', 'Uruguay': 'Uruguay',
    'Uzbekistan': 'Özbekistan', 'Vanuatu': 'Vanuatu', 'Venezuela': 'Venezuela', 'Vietnam': 'Vietnam', 'Wales': 'Galler',
    'Yemen': 'Yemen', 'Zambia': 'Zambiya', 'Zimbabwe': 'Zimbabve',
}
_TUR = {'EF': 'Son 16', 'QF': 'Çeyrek final', 'SF': 'Yarı final'}


def turkce(ad):
    """Milli takım adı (ya da eleme tablosundaki yer tutucu) Türkçe."""
    if ad in TR:
        return TR[ad]
    m = re.fullmatch(r'Winner (EF|QF|SF) (\d+)', ad)
    if m:
        return f'{_TUR[m[1]]} {m[2]}. maç galibi'
    m = re.fullmatch(r'Winner (\w+)/(\w+)', ad)
    if m:
        return f'{turkce(m[1])} / {turkce(m[2])} maçı galibi'
    m = re.fullmatch(r'([1-4])([A-L])', ad)
    if m:
        return f'{m[2]} Grubu {m[1]}.'
    m = re.fullmatch(r'3([A-L]{3,4})', ad)
    if m:
        return f'En iyi 3. ({"/".join(m[1])})'
    if '/' in ad:  # ortak ev sahipleri ('Saudi Arabia/Qatar')
        return ' / '.join(turkce(x) for x in ad.split('/'))
    return ad
