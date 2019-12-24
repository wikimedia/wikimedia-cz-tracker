{
	const idSupervisorNotes = document.querySelector( '#id_supervisor_notes' );

	function signSupervisor() {
		const param = `\n\nSem napište svou poznámku supervizora anebo tento text smažte --${window.username}`;
		idSupervisorNotes.value += param;
	}
	idSupervisorNotes.addEventListener( 'click', function cb() {
		signSupervisor();
		idSupervisorNotes.removeEventListener( 'click', cb );
	} );
}
{
	document.addEventListener( 'DOMContentLoaded', async () => {
		const topicsJson = await fetch( '/api/tracker/topics/?open_for_tickets=true' ),
			subtopicsJson = await fetch( '/api/tracker/subtopics/' );
		window.topicsList = await topicsJson.json();
		window.subtopicsList = await subtopicsJson.json();
		window.dispatchEvent( new CustomEvent( 'TopicsDataLoaded' ) );
	} );
}
