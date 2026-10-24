// trimmed from https://tiptravel.sk/search.json?ProductTypeIDs=401&DateFrom=01.07.2027&DateTo=31.08.2027&TransportationTypeID=201&AirportID=2&Sort=n&Page=1&PageSize=100 (2026-10-24)

;(async function() {     
	function zajazdy() { 
	var response = {
	"page": 1,
	"pageSize": 100,
	"sort": "n",
	"ProductTypeIDs":"401",
 
	
	
	
  

  	"codeid":"4153 r31 not-homepagex",

  "itemsCount": 0,
	"items": []

  

}

  
  //console.log(response.items)
  //console.log(response.items)
  if (!('items' in response)) {response.items=[]} //mh
  response.items = response.items.map(function(item) {
    item.accommodationName = item.accommodationName.replace(/\s*-\s*poznávací\szájazd|\s*-\s*pútnický\szájazd/i, '')
    item.url = item.url.replace(/^.*?\.sk/, '')
