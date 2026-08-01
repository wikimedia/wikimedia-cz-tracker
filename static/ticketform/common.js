{
	function statutoryDeclaration() {
		const fieldStatuatoryDeclaration = document.querySelector( '.field-statutory_declaration' ),
			idCarTravel = document.querySelector( '#id_car_travel' );

		if ( fieldStatuatoryDeclaration && idCarTravel ) {
			fieldStatuatoryDeclaration.hidden = !idCarTravel.checked;
		}
	}

	function getTopicById( topicId ) {
		for ( let i = 0; i < window.topicsList.length; i++ ) {
			const topicUrlSplit = window.topicsList[ i ].url.split( '/' );
			if ( topicId === topicUrlSplit[ topicUrlSplit.length - 2 ] ) {
				return window.topicsList[ i ];
			}
		}
	}

	function getSubtopicById( subtopicId ) {
		for ( let i = 0; i < window.subtopicsList.length; i++ ) {
			const subtopicUrlSplit = window.subtopicsList[ i ].url.split( '/' );
			if ( subtopicId === subtopicUrlSplit[ subtopicUrlSplit.length - 2 ] ) {
				return window.subtopicsList[ i ];
			}
		}
	}

	document.addEventListener( 'DOMContentLoaded', () => {
		const carTravelField = document.querySelector( '.field-car_travel' );

		if ( carTravelField ) {
			carTravelField.addEventListener( 'change', statutoryDeclaration );
		}

		statutoryDeclaration();
	} );
}
